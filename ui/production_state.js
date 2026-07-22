(function(root){
  const STAGES=[
    {key:'scope',number:1,label:'Phạm vi',summary:'Chọn sách/chương'},
    {key:'text',number:2,label:'Văn bản',summary:'Kiểm tra revision'},
    {key:'speakers',number:3,label:'Người nói',summary:'Chỉ xử lý exception'},
    {key:'voices',number:4,label:'Giọng',summary:'Cấu hình khi thiếu'},
    {key:'voice_map',number:5,label:'Duyệt bản đồ giọng',summary:'Approval riêng'},
    {key:'prepare',number:6,label:'Chuẩn bị',summary:'Không render'},
    {key:'render',number:7,label:'Render',summary:'Start riêng'},
    {key:'qa',number:8,label:'QA',summary:'Nghe và chốt'},
  ];
  const STAGE_INDEX=new Map(STAGES.map((stage,index)=>[stage.key,index]));
  const ACTIVE_JOB_STATUSES=new Set(['scheduled','queued','running','repairing','synthesizing','assembling','paused','interrupted']);
  const PREPARED_JOB_STATUSES=new Set(['prepared']);
  const TERMINAL_JOB_STATUSES=new Set(['completed','completed_with_errors','failed','cancelled']);
  const MUTATION_STATES=new Set(['CASTING_REVIEW','READY_TO_PREPARE','PREPARED','RENDERING_OR_PAUSED','RENDERED_NOT_QA']);
  const STAGE_PANEL_OWNERSHIP=[
    {id:'productionStageIsolation',stages:['scope','text','speakers','voices','voice_map','prepare','render','qa'],kind:'shell'},
    {id:'workspace',stages:['scope'],kind:'work'},
    {id:'productionQueuePanel',stages:['render'],kind:'work'},
    {id:'productionLegacyJobPanel',stages:['scope'],kind:'work'},
    {id:'flowStepSelectChapter',stages:['scope'],kind:'work'},
    {id:'flowStepReviewText',stages:['text'],kind:'work'},
    {id:'flowStepAssignVoices',stages:['speakers','voices'],kind:'work'},
    {id:'speakerReviewPanel',stages:['speakers'],kind:'work'},
    {id:'flowVoiceMemoryDetails',stages:['voices'],kind:'work'},
    {id:'flowStepReviewVoiceMap',stages:['voice_map'],kind:'work'},
    {id:'castingPlanPanel',stages:['voice_map'],kind:'work'},
    {id:'flowStepRenderChapter',stages:['prepare','render'],kind:'work'},
    {id:'renderPlanPanel',stages:['prepare','render'],kind:'work'},
    {id:'flowStepReviewAudio',stages:['qa'],kind:'work'},
    {id:'audioBox',stages:['qa'],kind:'work'},
    {id:'flowFinalApprovalPanel',stages:['qa'],kind:'work'},
  ];
  const STATE_META={
    NO_SCOPE:{stage:'scope',action:'SELECT_SCOPE',label:'Chọn phạm vi',title:'Chưa chọn chương sản xuất',target:'scope',explanation:'Hãy chọn một sách và một chương để bắt đầu quy trình sản xuất một chương.'},
    TEXT_BLOCKED:{stage:'text',action:'RESOLVE_TEXT',label:'Xử lý văn bản',title:'Văn bản chưa sẵn sàng',target:'text',explanation:'Cần có Text Revision active đã duyệt trước khi tiếp tục.'},
    SPEAKER_EXCEPTIONS:{stage:'speakers',action:'REVIEW_SPEAKERS',label:'Duyệt người nói',title:'Cần duyệt người nói',target:'speakers',explanation:'Speaker Draft chưa sẵn sàng hoặc còn dòng cần review.'},
    VOICE_BLOCKED:{stage:'voices',action:'CONFIGURE_VOICES',label:'Cấu hình giọng',title:'Cần cấu hình giọng',target:'voices',explanation:'Voice Profile hoặc effective voice chưa đủ an toàn để tạo Casting Plan.'},
    CASTING_REVIEW:{stage:'voice_map',action:'REVIEW_FINAL_VOICE_MAP',label:'Duyệt bản đồ giọng',title:'Bản đồ giọng đang chờ duyệt',target:'voice_map',explanation:'Speaker Draft đã duyệt; Casting Plan hiện tại vẫn là draft/unapproved; chưa có prepared job hay audio.'},
    READY_TO_PREPARE:{stage:'prepare',action:'PREPARE',label:'Chuẩn bị sản xuất',title:'Sẵn sàng chuẩn bị job audio',target:'prepare',explanation:'Casting Plan đã duyệt và chưa có job/audio active cho chương này.'},
    PREPARED:{stage:'render',action:'START_RENDER',label:'Bắt đầu render',title:'Job audio đã được chuẩn bị',target:'render',explanation:'Job đã ghim đầu vào và đang chờ lệnh start riêng; mở Production không tự render.'},
    RENDERING_OR_PAUSED:{stage:'render',action:'MONITOR_OR_RESUME',label:'Theo dõi tiến độ',title:'Job audio đang cần theo dõi',target:'render',explanation:'Đang có job active/resumable cho chương này; ưu tiên trạng thái job hơn cấu hình upstream.'},
    RENDERED_NOT_QA:{stage:'qa',action:'QA',label:'Kiểm tra chất lượng',title:'Audio đã tạo, chưa chốt Human QA',target:'qa',explanation:'Đã có active output; cần nghe QA trước khi đóng chu trình sản xuất.'},
    COMPLETE:{stage:'qa',action:'VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE',label:'Xem audio đã tạo',title:'Chương đã hoàn tất production',target:'qa',explanation:'Active output đã có dấu hiệu Human QA pass/accepted.'},
    STATE_UNRESOLVED:{stage:'scope',action:'RELOAD_READ_ONLY',label:'Tải lại trạng thái',title:'Không xác định được trạng thái an toàn',target:'diagnostics',explanation:'Dữ liệu đọc được đang thiếu hoặc mâu thuẫn; chỉ hiển thị chẩn đoán/read-only.'},
  };
  function n(value){const num=Number(value);return Number.isFinite(num)?num:0}
  function lower(value){return String(value||'').toLowerCase()}
  function stageKeysBefore(stageKey){const index=STAGE_INDEX.get(stageKey)??0;return STAGES.slice(0,index).map(stage=>stage.key)}
  function buildViewModel(conceptualState,overrides={}){
    const meta={...(STATE_META[conceptualState]||STATE_META.STATE_UNRESOLVED),...overrides};
    const currentStageKey=meta.stage;
    const completedStageKeys=overrides.completedStageKeys||stageKeysBefore(currentStageKey);
    const lockedStageKeys=STAGES.filter(stage=>!completedStageKeys.includes(stage.key)&&stage.key!==currentStageKey).map(stage=>stage.key);
    const stages=STAGES.map(stage=>({
      ...stage,
      current:stage.key===currentStageKey,
      complete:completedStageKeys.includes(stage.key),
      locked:lockedStageKeys.includes(stage.key),
      state:stage.key===currentStageKey?'current':completedStageKeys.includes(stage.key)?'complete':'locked',
    }));
    const viewModel={
      conceptualState,
      currentStageKey,
      currentStageLabel:STAGES.find(stage=>stage.key===currentStageKey)?.label||currentStageKey,
      completedStageKeys,
      lockedStageKeys,
      primaryActionKey:meta.action,
      primaryActionLabel:meta.label,
      title:meta.title,
      explanation:meta.explanation,
      blockerReason:meta.blockerReason||'',
      targetPanel:meta.target,
      mutationActionsMayBeDisplayed:MUTATION_STATES.has(conceptualState)&&!meta.readOnlyOnly,
      rangeReadinessAvailable:!!meta.rangeReadinessAvailable,
      diagnosticDetails:meta.diagnosticDetails||[],
      stages,
    };
    viewModel.stageSummaries=stageSummaries(viewModel);
    viewModel.panelStates=stagePanelStates(viewModel);
    return viewModel;
  }
  function stageSummaryText(stage,vm){
    if(stage.current)return vm.explanation||stage.summary;
    if(stage.complete)return `${stage.label} đã hoàn tất cho phạm vi hiện tại.`;
    return `${stage.label} đang khóa cho đến khi hoàn tất bước hiện tại.`;
  }
  function stageSummaries(vm){
    return vm.stages.map(stage=>({
      key:stage.key,
      label:stage.label,
      state:stage.state,
      text:stageSummaryText(stage,vm),
    }));
  }
  function stagePanelStates(vm,ownership=STAGE_PANEL_OWNERSHIP){
    const unresolved=vm?.conceptualState==='STATE_UNRESOLVED';
    return ownership.map(panel=>{
      const blockedNoScopeRange=vm?.conceptualState==='NO_SCOPE'&&panel.id==='productionLegacyJobPanel'&&!vm.rangeReadinessAvailable;
      const active=panel.kind==='shell'||(!unresolved&&!blockedNoScopeRange&&panel.stages.includes(vm?.currentStageKey));
      return {
        id:panel.id,
        kind:panel.kind,
        stages:[...panel.stages],
        active,
        hidden:!active,
        inert:!active,
        ariaHidden:active?'false':'true',
      };
    });
  }
  function hasValidScope(input){
    const bookId=n(input?.book?.id??input?.book_id);
    const chapter=input?.chapter||{};
    const chapterId=n(chapter.id??input?.chapter_id);
    return !!(bookId&&chapterId&&(!chapter.book_id||n(chapter.book_id)===bookId));
  }
  function hasApprovedActiveText(input){
    const activeId=n(input?.chapter?.active_text_revision_id??input?.active_text_revision_id);
    if(!activeId)return false;
    return (input?.revisions||[]).some(revision=>n(revision.id)===activeId&&lower(revision.status)==='approved');
  }
  function latestSpeakerDraft(input){
    if(input?.speakerDraft)return input.speakerDraft;
    const drafts=input?.speakerDrafts||[];
    return drafts.find(item=>!item.stale&&!item.load_error)||drafts[0]||null;
  }
  function planReviewComplete(input){
    const review=input?.casting?.casting?.plan?.source_metadata?.review||input?.casting?.casting?.source_metadata?.review||input?.casting?.source_metadata?.review;
    return !!review?.review_completed||(review?.remaining_unreviewed_count!==undefined&&n(review.remaining_unreviewed_count)===0);
  }
  function speakerBlocked(input){
    if(planReviewComplete(input))return '';
    const draft=latestSpeakerDraft(input);
    if(!draft)return input?.speakerRequired===false?'':'Chưa có Speaker Draft để xác nhận các dòng cần review.';
    if(draft.load_error)return 'Speaker Draft không tải được.';
    if(draft.stale)return 'Speaker Draft đã cũ so với text/casting hiện tại.';
    if(lower(draft.status)!=='approved')return 'Speaker Draft chưa được duyệt.';
    if(n(draft.remaining_unreviewed_count)>0)return 'Speaker Draft vẫn còn dòng chưa review.';
    if(n(draft.invalid_count)>0)return 'Speaker Draft còn dòng invalid.';
    return '';
  }
  function voiceBlocked(input){
    const validation=input?.casting?.voice_profile?.validation||input?.voice?.validation||{};
    if(validation&&validation.valid===false)return validation.reason||'Voice Profile chưa hợp lệ.';
    if(input?.voice?.valid===false)return input.voice.reason||'Effective voice chưa hợp lệ.';
    if(n(input?.voice?.missingEffectiveVoiceCount)>0)return 'Còn speaker chưa có effective voice.';
    const plan=input?.casting?.casting?.plan||input?.casting?.plan;
    const utterances=plan?.utterances||[];
    if(utterances.some(item=>item.resolved_voice_id===null||item.resolved_voice_id===''||item.resolved_voice_id===undefined))return 'Casting Plan có utterance chưa resolve voice.';
    return '';
  }
  function scopedJobs(input){
    const chapter=input?.chapter||{};
    const chapterNumber=n(chapter.chapter_number??input?.chapter_number);
    const bookId=n(input?.book?.id??chapter.book_id??input?.book_id);
    return (input?.jobs||[]).filter(job=>{
      const jobBook=n(job.book_id);
      if(jobBook&&bookId&&jobBook!==bookId)return false;
      const from=n(job.from_chapter),to=n(job.to_chapter);
      return chapterNumber&&from===chapterNumber&&to===chapterNumber;
    });
  }
  function activeOutput(input){return input?.active_output||input?.chapter?.active_output||{}}
  function humanQaAccepted(input){
    const approval=lower(input?.human_approval?.status||input?.chapter?.human_approval_status||input?.chapter?.human_qa_status);
    return ['approved','accepted','pass','human_qa_pass','human_qa_pass_with_minor_pronunciation_notes'].includes(approval);
  }
  function resolveProductionState(input={}){
    if(input.loading)return buildViewModel('STATE_UNRESOLVED',{title:'Đang tải trạng thái sản xuất',explanation:'Đang đọc trạng thái hiện tại; các hành động tạo job/render tạm thời không hiển thị.',readOnlyOnly:true,diagnosticDetails:['loading']});
    if(input.apiError)return buildViewModel('STATE_UNRESOLVED',{blockerReason:String(input.apiError),readOnlyOnly:true,diagnosticDetails:['api_error']});
    if(!hasValidScope(input))return buildViewModel('NO_SCOPE',{rangeReadinessAvailable:!!n(input?.book?.id??input?.book_id)});
    const jobs=scopedJobs(input);
    const liveJobs=jobs.filter(job=>PREPARED_JOB_STATUSES.has(lower(job.status))||ACTIVE_JOB_STATUSES.has(lower(job.status)));
    if(liveJobs.length>1)return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Có nhiều job active/resumable cho cùng một chương.',readOnlyOnly:true,diagnosticDetails:liveJobs.map(job=>`job:${job.id}:${job.status}`)});
    const active=activeOutput(input);
    const hasOutput=!!(active.active_output_job_id||active.active_output_artifact_id||input?.audio_artifact?.id||input?.chapter?.active_audio_artifact_id);
    if(hasOutput&&!(active.active_output_artifact_id||input?.audio_artifact?.id||input?.chapter?.active_audio_artifact_id)){
      return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Active output có job nhưng thiếu artifact.',readOnlyOnly:true,diagnosticDetails:['active_output_missing_artifact']});
    }
    if(hasOutput){
      if(humanQaAccepted(input))return buildViewModel('COMPLETE',{completedStageKeys:STAGES.map(stage=>stage.key)});
      return buildViewModel('RENDERED_NOT_QA');
    }
    if(liveJobs.length===1){
      const job=liveJobs[0],status=lower(job.status);
      if(PREPARED_JOB_STATUSES.has(status)){
        const missing=[];
        if(!n(job.casting_plan_id))missing.push('casting_plan_id');
        if(!n(job.from_chapter)||!n(job.to_chapter))missing.push('chapter_range');
        if(missing.length)return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Prepared job thiếu snapshot bắt buộc.',readOnlyOnly:true,diagnosticDetails:missing});
        return buildViewModel('PREPARED',{explanation:`Job #${job.id} đã prepared và chỉ render sau lệnh Start riêng.`});
      }
      return buildViewModel('RENDERING_OR_PAUSED',{explanation:`Job #${job.id} đang ở trạng thái ${job.status}.`});
    }
    if(TERMINAL_JOB_STATUSES.has(lower(input?.chapter?.audio_status))&&!hasOutput){
      return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Trạng thái chương báo completed/terminal nhưng không có active output.',readOnlyOnly:true,diagnosticDetails:['terminal_without_output']});
    }
    if(!hasApprovedActiveText(input))return buildViewModel('TEXT_BLOCKED');
    const speakerReason=speakerBlocked(input);
    if(speakerReason)return buildViewModel('SPEAKER_EXCEPTIONS',{blockerReason:speakerReason,explanation:speakerReason});
    const voiceReason=voiceBlocked(input);
    if(voiceReason)return buildViewModel('VOICE_BLOCKED',{blockerReason:voiceReason,explanation:voiceReason});
    const casting=input?.casting?.casting||input?.casting||{};
    if(!casting.id)return buildViewModel('CASTING_REVIEW',{title:'Chưa có bản đồ giọng cuối',explanation:'Cần tạo/kiểm tra Final Voice Map draft trước khi approve.'});
    const planStatus=lower(casting.status);
    if(planStatus==='draft')return buildViewModel('CASTING_REVIEW');
    if(planStatus!=='approved')return buildViewModel('STATE_UNRESOLVED',{blockerReason:`Casting Plan có trạng thái không hỗ trợ: ${casting.status}`,readOnlyOnly:true,diagnosticDetails:['unsupported_casting_status']});
    return buildViewModel('READY_TO_PREPARE');
  }
  function productionScopeFromHash(hash){
    const raw=String(hash||'').replace(/^#/,'');
    const [path,query='']=raw.split('?');
    const route=path.replace(/^\//,'')||'home';
    const params=new URLSearchParams(query);
    const bookId=n(params.get('book'));
    const chapterId=n(params.get('chapter'));
    return {route,explicit:route==='production'&&(bookId||chapterId),bookId:bookId||null,chapterId:chapterId||null};
  }
  function productionHashForScope(scope){
    const bookId=n(scope?.bookId??scope?.book_id??scope?.book?.id);
    const chapterId=n(scope?.chapterId??scope?.chapter_id??scope?.chapter?.id);
    if(!bookId||!chapterId)return '#/production';
    return `#/production?book=${bookId}&chapter=${chapterId}`;
  }
  const api={STAGES,STAGE_PANEL_OWNERSHIP,resolveProductionState,productionScopeFromHash,productionHashForScope,stagePanelStates};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.ProductionWorkflow=api;
})(typeof window!=='undefined'?window:globalThis);
