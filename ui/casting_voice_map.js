/* DAILY-PROD-2B1: Final Voice Map catalog/provenance overlay.
 * This file intentionally does not create new mutation paths. It reads the
 * current draft plan and shared voice catalog that app.js already loaded.
 */
(function(){
  function safeText(value){return String(value ?? '')}
  function html(value){return esc(safeText(value))}

  function resolutionSource(resolution){
    return safeText(resolution?.resolution_source || resolution?.source || 'unresolved')
  }

  function catalogState(voiceId){
    if (typeof voiceCatalogState === 'function') return voiceCatalogState(voiceId)
    if (!voiceId) return {label:'Unresolved',kind:'missing',provenance:'Chưa có giọng hiệu lực.',blocked:true}
    const item = typeof voiceCatalogItem === 'function' ? voiceCatalogItem(String(voiceId)) : null
    if (!item) return {label:String(voiceId),kind:'legacy',provenance:`Legacy / unavailable: ${voiceId}`,blocked:true}
    if (item.source_kind === 'preset') return {label:item.display_name,kind:'preset',provenance:item.provenance_summary || 'Preset VieNeu voice',blocked:item.selectable === false}
    return {label:`${item.display_name} (Custom)`,kind:'custom',provenance:typeof selectedVoiceProvenance === 'function' ? selectedVoiceProvenance(voiceId) : item.provenance_summary,blocked:item.selectable === false}
  }

  function currentPlan(){
    return state?.casting?.casting?.plan || {utterances:[]}
  }

  function currentResolution(utterance){
    return typeof utteranceResolution === 'function' ? utteranceResolution(utterance) : null
  }

  function usageSummary(plan){
    const counts = new Map()
    ;(plan?.utterances || []).forEach((utterance) => {
      const resolution = currentResolution(utterance)
      const voiceId = resolution?.resolved_voice_id || ''
      const source = resolutionSource(resolution)
      const key = `${voiceId}|${source}`
      if (!counts.has(key)) {
        counts.set(key, {voiceId, source, count:0, unknown:0, state:catalogState(voiceId)})
      }
      const item = counts.get(key)
      item.count += 1
      if (utterance.role === 'unknown') item.unknown += 1
    })
    return Array.from(counts.values()).sort((a,b) => b.count - a.count || safeText(a.voiceId).localeCompare(safeText(b.voiceId)))
  }

  function renderUsageSummary(){
    const target = document.querySelector('#flowVoiceUsageSummary')
    if (!target) return
    const summary = usageSummary(currentPlan())
    const blocked = summary.filter(item => item.state.blocked)
    if (!summary.length) {
      target.innerHTML = '<p class="muted">Chưa có voice usage để tóm tắt.</p>'
      return
    }
    target.innerHTML = `<div class="voice-usage-grid">${summary.map(item => `<div class="voice-usage-card ${item.state.blocked ? 'blocked' : ''}"><strong>${html(item.state.label)}</strong><span>${html(item.voiceId || 'unresolved')} · ${html(item.state.kind)} · ${item.count} assignment${item.count === 1 ? '' : 's'}</span><small>${html(sourceLabels[item.source] || item.source)}${item.unknown ? ` · ${item.unknown} unknown fallback` : ''}</small><small>${html(item.state.provenance)}</small></div>`).join('')}</div>${blocked.length ? `<div class="issue warning">Có ${blocked.length} voice selection không khả dụng trong catalog hiện tại. Giá trị cũ được giữ nguyên, không tự thay thế.</div>` : ''}`
  }

  if (typeof speakerStatusSummary === 'function') {
    const originalSpeakerStatusSummary = speakerStatusSummary
    speakerStatusSummary = function(resolution, flags){
      const status = originalSpeakerStatusSummary(resolution, flags)
      const voiceState = catalogState(resolution?.resolved_voice_id)
      if (voiceState.blocked) {
        return {
          label: 'Giọng không khả dụng',
          className: 'missing',
          nextAction: 'Giá trị cũ được giữ để audit; hãy chọn một giọng khả dụng rồi lưu draft mới nếu cần sửa.'
        }
      }
      const source = resolutionSource(resolution)
      if (flags?.isUnknownFallback && !resolution?.needs_review) {
        return {...status, label:'Đang dùng unknown fallback'}
      }
      if (['book_male','book_female','narrator','unknown_fallback'].includes(source) && status.className !== 'missing') {
        return {...status, label:'Đang dùng giọng mặc định'}
      }
      return status
    }
  }

  if (typeof buildVoiceMapRows === 'function') {
    const originalBuildVoiceMapRows = buildVoiceMapRows
    buildVoiceMapRows = function(context, plan){
      const rows = originalBuildVoiceMapRows(context, plan)
      const counts = new Map()
      ;(plan?.utterances || []).forEach((utterance) => {
        const key = `${utterance.role}:${utterance.character_id || 0}`
        counts.set(key, (counts.get(key) || 0) + 1)
      })
      rows.forEach((row) => {
        const matching = (plan?.utterances || []).find((utterance) =>
          speakerName(utterance.role, utterance.character_id) === row.speaker
        )
        const resolution = currentResolution(matching || {})
        const voiceId = resolution?.resolved_voice_id || ''
        const voiceState = catalogState(voiceId)
        row.voice = voiceState.label
        row.voiceKey = voiceId
        row.voiceKind = voiceState.kind
        row.provenance = voiceState.provenance
        row.count = counts.get(`${matching?.role}:${matching?.character_id || 0}`) || 1
      })
      return rows
    }
  }

  function enhanceVoiceMapRows(){
    const table = document.querySelector('#flowVoiceMapTable')
    if (!table || !state?.casting?.casting?.plan) return
    renderUsageSummary()
    Array.from(table.querySelectorAll('.flow-voice-map-row')).forEach((row, index) => {
      const data = (typeof buildVoiceMapRows === 'function' ? buildVoiceMapRows(state.casting, currentPlan()) : [])[index]
      if (!data || row.dataset.voiceMapEnhanced === '1') return
      const voiceColumn = row.children[2]
      if (!voiceColumn) return
      const detail = document.createElement('small')
      detail.className = 'voice-provenance'
      detail.textContent = `${data.voiceKey || 'unresolved'} · ${data.voiceKind} · ${data.count || 1} dòng. ${data.provenance || ''}`
      voiceColumn.appendChild(detail)
      const roleColumn = row.children[1]
      if (roleColumn) {
        const note = document.createElement('small')
        note.textContent = 'Speaker identity remains separate from voice selection.'
        roleColumn.appendChild(note)
      }
      row.dataset.voiceMapEnhanced = '1'
    })
  }

  document.addEventListener('DOMContentLoaded', () => {
    const table = document.querySelector('#flowVoiceMapTable')
    if (!table) return
    new MutationObserver(enhanceVoiceMapRows).observe(table, {childList:true, subtree:false})
    enhanceVoiceMapRows()
  })
})()
