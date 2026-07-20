/* DAILY-PROD-2B2: safe contextual detour to Voice Library.
 * The detour stores only same-tab UI navigation context. It never saves an
 * assignment, approves a plan, prepares a job, starts render, or calls TTS.
 */
(function(root){
  const STORAGE_KEY = 'storyAudio.voiceDetour.v1'
  const MAX_AGE_MS = 2 * 60 * 60 * 1000
  const ROUTES = new Set(['production', 'voices', 'books'])
  const DESTINATIONS = new Set(['voices', 'books'])
  const ORIGINS = new Set(['book_profile', 'character_override', 'casting_plan', 'production_voice_blocker'])
  const ACTIONS = new Set(['create_voice', 'choose_voice', 'configure_book_voice', 'configure_character_override'])
  const PROFILE_FIELDS = new Set(['profileNarratorVoice', 'profileMaleVoice', 'profileFemaleVoice', 'profileExplicitVoice'])
  const FIXED_FIELDS = new Set(['flowVoiceMapTable', 'flowAssignWarnings'])

  function appState(){ return root.storyAudioAppState || root.state || {} }
  function nowMs(){ return Date.now() }
  function safeNumber(value){
    const number = Number(value)
    return Number.isInteger(number) && number > 0 ? number : null
  }
  function fieldAllowed(value){
    const field = String(value || '')
    return PROFILE_FIELDS.has(field) || FIXED_FIELDS.has(field) || /^character-voice-\d+$/.test(field)
  }
  function routeHash(route, context){
    if (route === 'production' && context?.bookId && context?.chapterId) {
      return `#/production?book=${context.bookId}&chapter=${context.chapterId}`
    }
    return route === 'books' ? '#/books' : route === 'voices' ? '#/voices' : '#/home'
  }
  function normalizeContext(input, clock = nowMs()){
    const source = input && typeof input === 'object' ? input : {}
    const createdAt = safeNumber(source.createdAt) || clock
    const age = clock - createdAt
    if (age < 0 || age > MAX_AGE_MS) return null
    const originRoute = String(source.originRoute || 'production')
    const returnRoute = String(source.returnRoute || originRoute)
    const destination = String(source.destination || 'voices')
    const originType = String(source.originType || '')
    const operation = String(source.operation || 'create_voice')
    const fieldId = String(source.fieldId || '')
    if (!ROUTES.has(originRoute) || !ROUTES.has(returnRoute) || !DESTINATIONS.has(destination)) return null
    if (!ORIGINS.has(originType) || !ACTIONS.has(operation) || !fieldAllowed(fieldId)) return null
    const bookId = safeNumber(source.bookId)
    const chapterId = safeNumber(source.chapterId)
    if (returnRoute === 'production' && (!bookId || !chapterId)) return null
    const context = {
      schema: 1,
      originRoute,
      returnRoute,
      destination,
      originType,
      operation,
      fieldId,
      bookId,
      chapterId,
      characterId: safeNumber(source.characterId),
      castingPlanId: safeNumber(source.castingPlanId),
      castingPlanRevision: safeNumber(source.castingPlanRevision),
      selectedAssignmentKey: typeof source.selectedAssignmentKey === 'string' ? source.selectedAssignmentKey : '',
      createdVoiceId: safeNumber(source.createdVoiceId),
      createdAssignmentKey: typeof source.createdAssignmentKey === 'string' ? source.createdAssignmentKey : '',
      hasUnsavedDraft: !!source.hasUnsavedDraft,
      sourceDraft: sanitizeDraft(source.sourceDraft),
      createdAt,
    }
    if (context.originType === 'character_override' && !context.characterId) return null
    if (context.originType === 'casting_plan' && (!context.castingPlanId || !context.castingPlanRevision)) return null
    return context
  }
  function sanitizeDraft(draft){
    if (!draft || typeof draft !== 'object') return null
    const clean = {}
    Object.entries(draft).forEach(([key, value]) => {
      const stableKey = String(key)
      if (!fieldAllowed(stableKey) && !['profileUnknownFallback', 'newCharacterAssignment', 'newCharacterVoice'].includes(stableKey)) return
      if (typeof value === 'string' && value.length <= 200) clean[stableKey] = value
    })
    return Object.keys(clean).length ? clean : null
  }
  function storage(){
    try { return root.sessionStorage || null } catch { return null }
  }
  function saveContext(context){
    const normalized = normalizeContext(context)
    if (!normalized) return null
    storage()?.setItem(STORAGE_KEY, JSON.stringify(normalized))
    return normalized
  }
  function loadContext(){
    try {
      const normalized = normalizeContext(JSON.parse(storage()?.getItem(STORAGE_KEY) || 'null'))
      if (!normalized) clearContext()
      return normalized
    } catch {
      clearContext()
      return null
    }
  }
  function clearContext(){ storage()?.removeItem(STORAGE_KEY) }
  function byId(id){ return root.document?.getElementById(id) || null }
  function speak(message, error = false){
    const banner = byId('voiceDetourStatus')
    if (banner) {
      banner.textContent = message
      banner.classList.toggle('error-text', !!error)
    }
    if (typeof root.toast === 'function') root.toast(message, error)
  }
  function currentVoiceKeyForContext(context){
    if (context.createdAssignmentKey) return context.createdAssignmentKey
    if (context.createdVoiceId) return `custom:${context.createdVoiceId}`
    if (appState()?.selectedVoiceId) return `custom:${appState().selectedVoiceId}`
    return ''
  }
  function catalogItem(key){
    return typeof root.voiceCatalogItem === 'function' ? root.voiceCatalogItem(key) : null
  }
  async function refreshCatalog(){
    if (typeof root.loadVoiceCatalog === 'function') await root.loadVoiceCatalog()
    if (typeof root.loadCustomVoices === 'function') await root.loadCustomVoices()
  }
  function validateReturnTarget(context, assignmentKey = ''){
    if (!normalizeContext(context)) return {ok:false, reason:'Return context is malformed or expired.'}
    if (context.returnRoute === 'production') {
      const chapter = appState()?.dialog?.chapter
      if (chapter && Number(chapter.id) !== Number(context.chapterId)) return {ok:false, reason:'Source chapter changed during the detour.'}
    }
    if (context.originType === 'casting_plan') {
      const casting = appState()?.casting?.casting
      if (!casting || Number(casting.id) !== Number(context.castingPlanId) || Number(casting.plan_revision) !== Number(context.castingPlanRevision) || casting.status !== 'draft') {
        return {ok:false, reason:'Final Voice Map changed; the stale voice edit was not applied.'}
      }
    }
    if (context.originType === 'character_override') {
      const exists = (appState()?.casting?.characters || []).some(item => Number(item.id) === Number(context.characterId))
      if (!exists) return {ok:false, reason:'Character no longer exists; the voice edit was not applied.'}
    }
    if (assignmentKey) {
      const item = catalogItem(assignmentKey)
      if (!item || item.selectable === false || item.active === false) return {ok:false, reason:'The voice is not selectable yet. Add a usable revision first.'}
    }
    return {ok:true}
  }
  function collectSourceDraft(context){
    const draft = {}
    PROFILE_FIELDS.forEach(id => { const el = byId(id); if (el) draft[id] = el.value || '' })
    const fallback = byId('profileUnknownFallback')
    if (fallback) draft.profileUnknownFallback = fallback.value || ''
    if (context?.originType === 'character_override' && context.characterId) {
      const assignment = byId(`character-assignment-${context.characterId}`)
      const voice = byId(`character-voice-${context.characterId}`)
      if (assignment) draft[`character-assignment-${context.characterId}`] = assignment.value || ''
      if (voice) draft[`character-voice-${context.characterId}`] = voice.value || ''
    }
    return sanitizeDraft(draft)
  }
  function restoreDraft(context){
    const draft = context?.sourceDraft || {}
    Object.entries(draft).forEach(([id, value]) => {
      const el = byId(id)
      if (el) el.value = value
    })
    if (typeof root.profileFallbackChanged === 'function') root.profileFallbackChanged()
    if (typeof root.renderProfileProvenance === 'function') root.renderProfileProvenance()
  }
  function applyUnsavedPreselection(context, assignmentKey){
    if (!assignmentKey) return false
    const validation = validateReturnTarget(context, assignmentKey)
    if (!validation.ok) {
      speak(validation.reason, true)
      return false
    }
    const field = byId(context.fieldId)
    if (!field || field.tagName !== 'SELECT') return false
    field.value = assignmentKey
    field.dataset.voiceDetourUnsaved = '1'
    if (context.originType === 'character_override') {
      const assignment = byId(`character-assignment-${context.characterId}`)
      if (assignment) assignment.value = 'custom'
      field.classList.remove('hidden')
      const provenance = byId(`character-voice-provenance-${context.characterId}`)
      if (provenance && typeof root.selectedVoiceProvenance === 'function') provenance.textContent = root.selectedVoiceProvenance(assignmentKey)
    } else if (typeof root.renderProfileProvenance === 'function') {
      root.renderProfileProvenance()
    }
    markUnsaved(field)
    return true
  }
  function markUnsaved(field){
    let note = root.document?.querySelector?.('[data-voice-detour-unsaved-note="1"]')
    if (!note) {
      note = root.document.createElement('div')
      note.className = 'issue warning voice-detour-unsaved-note'
      note.dataset.voiceDetourUnsavedNote = '1'
      note.setAttribute('role', 'status')
      field.closest('label, .metadata-grid, .voice-profile-card, .character-card')?.appendChild(note)
    }
    note.textContent = 'Giọng đã có trong danh sách và đang được chọn tạm thời. Hãy kiểm tra rồi bấm Lưu nếu muốn áp dụng.'
  }
  async function restoreContext({cancel = false} = {}){
    const context = loadContext()
    if (!context) {
      speak('Không có đường quay lại hợp lệ từ Thư viện giọng.', true)
      return false
    }
    const assignmentKey = cancel ? '' : currentVoiceKeyForContext(context)
    try {
      if (context.returnRoute === 'production') {
        if (typeof root.setAppRoute === 'function') root.setAppRoute('production')
        else root.location.hash = routeHash('production', context)
        if (typeof root.history?.replaceState === 'function') root.history.replaceState(null, '', routeHash('production', context))
        if (!appState()?.books?.length && typeof root.loadBooks === 'function') await root.loadBooks()
        const book = appState()?.books?.find(item => Number(item.id) === Number(context.bookId))
        if (book && appState()) appState().book = book
        if (typeof root.openChapter === 'function') await root.openChapter(context.chapterId, {initialTab:'casting', replaceScopeRoute:true})
        await refreshCatalog()
        if (typeof root.openCasting === 'function') await root.openCasting()
      } else if (typeof root.setAppRoute === 'function') {
        root.setAppRoute(context.returnRoute)
      } else {
        root.location.hash = routeHash(context.returnRoute, context)
      }
      restoreDraft(context)
      const applied = !cancel && applyUnsavedPreselection(context, assignmentKey)
      clearContext()
      setTimeout(() => {
        const target = byId(context.fieldId) || byId('flowVoiceMapTable') || byId('productionCurrentWorkArea')
        target?.scrollIntoView?.({block:'center', behavior:'smooth'})
        target?.focus?.()
      }, 0)
      speak(cancel ? 'Đã hủy đường vòng. Chưa có thay đổi nào được lưu.' : applied ? 'Giọng mới đã được đưa vào ô chọn dưới dạng chưa lưu. Hãy kiểm tra rồi bấm Lưu.' : 'Đã quay lại đúng ngữ cảnh. Hãy chọn giọng trong danh sách rồi bấm Lưu nếu cần.')
      return true
    } catch (error) {
      clearContext()
      speak(error?.message || 'Không thể quay lại ngữ cảnh cũ.', true)
      return false
    }
  }
  function navigateToDestination(context){
    const destination = context.destination || 'voices'
    if (typeof root.setAppRoute === 'function') root.setAppRoute(destination)
    else root.location.hash = routeHash(destination, context)
    if (typeof root.history?.replaceState === 'function') root.history.replaceState(null, '', `${routeHash(destination, context)}?detour=voice-setup`)
    renderDetourBanner()
  }
  function beginDetour(context){
    const normalized = normalizeContext({...context, createdAt: nowMs()})
    if (!normalized) {
      speak('Không thể mở đường vòng vì ngữ cảnh không hợp lệ.', true)
      return null
    }
    normalized.sourceDraft = collectSourceDraft(normalized)
    normalized.hasUnsavedDraft = !!normalized.sourceDraft
    const saved = saveContext(normalized)
    if (!saved) return null
    navigateToDestination(saved)
    speak('Đã mở Thư viện giọng. Tạo hoặc cấu hình giọng xong thì quay lại nơi chọn giọng.')
    return saved
  }
  function contextFromButton(button){
    const chapter = appState()?.dialog?.chapter || {}
    const casting = appState()?.casting?.casting || {}
    const type = button.dataset.voiceDetourOrigin
    const fieldId = button.dataset.voiceDetourField
    return normalizeContext({
      originRoute: 'production',
      returnRoute: 'production',
      destination: button.dataset.voiceDetourDestination || 'voices',
      originType: type,
      operation: button.dataset.voiceDetourOperation || 'create_voice',
      fieldId,
      bookId: safeNumber(button.dataset.bookId) || safeNumber(chapter.book_id),
      chapterId: safeNumber(button.dataset.chapterId) || safeNumber(chapter.id),
      characterId: safeNumber(button.dataset.characterId),
      castingPlanId: safeNumber(button.dataset.castingPlanId) || safeNumber(casting.id),
      castingPlanRevision: safeNumber(button.dataset.castingPlanRevision) || safeNumber(casting.plan_revision),
      selectedAssignmentKey: byId(fieldId)?.value || '',
    })
  }
  function detourButton(label, context){
    return `<button type="button" class="ghost voice-detour-button" data-voice-detour="1" data-voice-detour-origin="${context.originType}" data-voice-detour-field="${context.fieldId}" data-voice-detour-operation="${context.operation || 'create_voice'}" data-voice-detour-destination="${context.destination || 'voices'}" data-book-id="${context.bookId || ''}" data-chapter-id="${context.chapterId || ''}" data-character-id="${context.characterId || ''}" data-casting-plan-id="${context.castingPlanId || ''}" data-casting-plan-revision="${context.castingPlanRevision || ''}">${label}</button>`
  }
  function enhanceProfileFields(){
    const chapter = appState()?.dialog?.chapter || {}
    if (!chapter.id || !chapter.book_id) return
    PROFILE_FIELDS.forEach(fieldId => {
      const select = byId(fieldId)
      if (!select || select.dataset.voiceDetourEnhanced === '1') return
      select.dataset.voiceDetourEnhanced = '1'
      select.insertAdjacentHTML('afterend', `<div class="voice-detour-actions">${detourButton('Thêm giọng mới', {originType:'book_profile', fieldId, operation:'create_voice', bookId:chapter.book_id, chapterId:chapter.id})}${detourButton('Quản lý giọng', {originType:'book_profile', fieldId, operation:'choose_voice', bookId:chapter.book_id, chapterId:chapter.id})}</div>`)
    })
  }
  function enhanceCharacterFields(){
    const chapter = appState()?.dialog?.chapter || {}
    if (!chapter.id || !chapter.book_id) return
    root.document?.querySelectorAll?.('select[id^="character-voice-"]').forEach(select => {
      if (select.dataset.voiceDetourEnhanced === '1') return
      const characterId = safeNumber(select.id.replace('character-voice-', ''))
      if (!characterId) return
      select.dataset.voiceDetourEnhanced = '1'
      select.insertAdjacentHTML('afterend', `<div class="voice-detour-actions">${detourButton('Thêm giọng mới', {originType:'character_override', fieldId:select.id, operation:'create_voice', bookId:chapter.book_id, chapterId:chapter.id, characterId})}${detourButton('Quản lý giọng nhân vật', {originType:'character_override', fieldId:select.id, operation:'configure_character_override', bookId:chapter.book_id, chapterId:chapter.id, characterId})}</div>`)
    })
  }
  function enhanceCastingPlan(){
    const note = byId('flowVoiceMapCatalogNote')
    const casting = appState()?.casting?.casting || {}
    const chapter = appState()?.dialog?.chapter || {}
    if (!chapter.id || !chapter.book_id) return
    if (note && casting.id && note.dataset.voiceDetourEnhanced !== '1') {
      note.dataset.voiceDetourEnhanced = '1'
      note.insertAdjacentHTML('afterend', `<div class="voice-detour-actions voice-map-detour">${detourButton('Quản lý giọng trong Thư viện', {originType:'casting_plan', fieldId:'flowVoiceMapTable', operation:'choose_voice', bookId:chapter.book_id, chapterId:chapter.id, castingPlanId:casting.id, castingPlanRevision:casting.plan_revision})}<span class="muted">Quay lại đây sẽ chỉ làm mới catalog; lưu draft và duyệt plan vẫn là thao tác riêng.</span></div>`)
    }
    const warnings = byId('flowAssignWarnings')
    if (warnings && warnings.dataset.voiceDetourEnhanced !== '1') {
      warnings.dataset.voiceDetourEnhanced = '1'
      warnings.insertAdjacentHTML('afterend', `<div class="voice-detour-actions">${detourButton('Cấu hình giọng còn thiếu', {originType:'production_voice_blocker', fieldId:'flowAssignWarnings', operation:'configure_book_voice', bookId:chapter.book_id, chapterId:chapter.id})}</div>`)
    }
  }
  function enhanceOrigins(){
    enhanceProfileFields()
    enhanceCharacterFields()
    enhanceCastingPlan()
  }
  function targetVoiceUsable(context){
    const key = currentVoiceKeyForContext(context)
    if (!key) return false
    const item = catalogItem(key)
    return !!item && item.selectable !== false && item.active !== false
  }
  function renderDetourBanner(){
    const view = byId('voicesView')
    if (!view) return
    let banner = byId('voiceDetourBanner')
    if (!banner) {
      banner = root.document.createElement('section')
      banner.id = 'voiceDetourBanner'
      banner.className = 'panel voice-detour-banner hidden'
      banner.innerHTML = '<div><p class="eyebrow">Đường vòng chọn giọng</p><h2>Quay lại đúng nơi đang cấu hình</h2><p id="voiceDetourStatus" class="muted" role="status"></p></div><div class="voice-detour-banner-actions"><button id="voiceDetourReturn" class="primary" type="button">Quay lại nơi chọn giọng</button><button id="voiceDetourCancel" class="secondary" type="button">Hủy đường vòng</button></div>'
      view.insertBefore(banner, view.firstElementChild)
    }
    const context = loadContext()
    banner.classList.toggle('hidden', !context)
    if (!context) return
    const usable = targetVoiceUsable(context)
    const key = currentVoiceKeyForContext(context)
    byId('voiceDetourStatus').textContent = usable ? `${key} đã có trong catalog. Quay lại sẽ chỉ chọn tạm thời, chưa lưu.` : 'Hãy tạo voice và thêm revision usable. Nếu chưa xong, quay lại sẽ không tự chọn giọng.'
    byId('voiceDetourReturn').onclick = () => restoreContext()
    byId('voiceDetourCancel').onclick = () => restoreContext({cancel:true})
  }
  async function afterVoiceMutation(){
    const context = loadContext()
    if (!context) return
    if (appState()?.selectedVoiceId) {
      context.createdVoiceId = safeNumber(appState().selectedVoiceId)
      context.createdAssignmentKey = context.createdVoiceId ? `custom:${context.createdVoiceId}` : ''
      saveContext(context)
    }
    await refreshCatalog().catch(() => {})
    renderDetourBanner()
  }
  function wrapLibraryHandlers(){
    const createButton = byId('libraryCreate')
    if (createButton && createButton.dataset.voiceDetourWrapped !== '1' && typeof root.createLibraryVoice === 'function') {
      const original = root.createLibraryVoice
      root.createLibraryVoice = async function(...args){ const result = await original.apply(this, args); await afterVoiceMutation(); return result }
      createButton.onclick = root.createLibraryVoice
      createButton.dataset.voiceDetourWrapped = '1'
    }
    const uploadButton = byId('libraryUploadRevision')
    if (uploadButton && uploadButton.dataset.voiceDetourWrapped !== '1' && typeof root.uploadLibraryRevision === 'function') {
      const original = root.uploadLibraryRevision
      root.uploadLibraryRevision = async function(...args){ const result = await original.apply(this, args); await afterVoiceMutation(); return result }
      uploadButton.onclick = root.uploadLibraryRevision
      uploadButton.dataset.voiceDetourWrapped = '1'
    }
    if (typeof root.setPreferredSynthesisRevision === 'function' && !root.setPreferredSynthesisRevision.voiceDetourWrapped) {
      const original = root.setPreferredSynthesisRevision
      const wrapped = async function(...args){ const result = await original.apply(this, args); await afterVoiceMutation(); return result }
      wrapped.voiceDetourWrapped = true
      root.setPreferredSynthesisRevision = wrapped
    }
  }
  function bindDom(){
    root.document?.addEventListener?.('click', event => {
      const button = event.target?.closest?.('[data-voice-detour]')
      if (!button) return
      event.preventDefault()
      const context = contextFromButton(button)
      beginDetour(context)
    })
    root.addEventListener?.('hashchange', renderDetourBanner)
    const observer = new MutationObserver(() => {
      enhanceOrigins()
      renderDetourBanner()
      wrapLibraryHandlers()
    })
    observer.observe(root.document.body, {childList:true, subtree:true})
    enhanceOrigins()
    renderDetourBanner()
    wrapLibraryHandlers()
  }
  const exported = {
    STORAGE_KEY,
    MAX_AGE_MS,
    normalizeContext,
    routeHash,
    saveContext,
    loadContext,
    clearContext,
    beginDetour,
    restoreContext,
    validateReturnTarget,
  }
  root.StoryAudioVoiceDetour = exported
  if (typeof module !== 'undefined' && module.exports) module.exports = exported
  if (root.document?.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', bindDom)
  else if (root.document?.body) bindDom()
})(typeof globalThis !== 'undefined' ? globalThis : window)
