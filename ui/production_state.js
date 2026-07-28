(function(root){
  const STAGES=[
    {key:'scope',number:1,label:'Phạm vi',summary:'Chọn sách và chương'},
    {key:'text',number:2,label:'Văn bản',summary:'Duyệt nội dung'},
    {key:'speakers',number:3,label:'Người nói',summary:'Xác nhận lời thoại'},
    {key:'voices',number:4,label:'Giọng',summary:'Gán giọng đọc'},
    {key:'voice_map',number:5,label:'Phân vai',summary:'Duyệt phân vai'},
    {key:'prepare',number:6,label:'Chuẩn bị',summary:'Chuẩn bị audio'},
    {key:'render',number:7,label:'Tạo audio',summary:'Tạo bản nghe'},
    {key:'qa',number:8,label:'Duyệt audio',summary:'Nghe và duyệt'},
  ];
  const PHASES=[
    {key:'scope',number:1,label:'Chọn chương',summary:'Chọn sách và phạm vi'},
    {key:'content',number:2,label:'Xác nhận nội dung và người nói',summary:'Duyệt nội dung, xác nhận từng người nói'},
    {key:'voice',number:3,label:'Gán và duyệt giọng',summary:'Chọn giọng, lưu nháp rồi duyệt'},
    {key:'render',number:4,label:'Chuẩn bị và render',summary:'Cố định đầu vào rồi tạo audio'},
    {key:'qa',number:5,label:'Nghe và duyệt',summary:'Nghe bản cuối và ghi kết luận'},
    {key:'done',number:6,label:'Hoàn tất và tải xuống',summary:'Mở audio đã duyệt và tải xuống'},
  ];
  const STATE_PHASE={
    NO_SCOPE:'scope',
    TEXT_BLOCKED:'content',
    SPEAKER_EXCEPTIONS:'content',
    VOICE_BLOCKED:'voice',
    CASTING_REVIEW:'voice',
    READY_TO_PREPARE:'voice',
    PREPARED:'render',
    RENDERING_OR_PAUSED:'render',
    RENDERED_NOT_QA:'qa',
    COMPLETE:'done',
    STATE_UNRESOLVED:'scope',
  };
  const STAGE_INDEX=new Map(STAGES.map((stage,index)=>[stage.key,index]));
  const ACTIVE_JOB_STATUSES=new Set(['scheduled','queued','running','repairing','synthesizing','assembling','paused','interrupted']);
  const PREPARED_JOB_STATUSES=new Set(['prepared']);
  const TERMINAL_JOB_STATUSES=new Set(['completed','completed_with_errors','failed','cancelled']);
  const MUTATION_STATES=new Set(['CASTING_REVIEW','READY_TO_PREPARE','PREPARED','RENDERING_OR_PAUSED','RENDERED_NOT_QA']);
  const STAGE_PANEL_OWNERSHIP=[
    {id:'productionStageIsolation',stages:['scope','text','speakers','voices','voice_map','prepare','render','qa'],kind:'shell'},
    {id:'workspace',stages:['scope','prepare'],kind:'work'},
    {id:'productionQueuePanel',stages:['render'],kind:'work'},
    {id:'productionLegacyJobPanel',stages:[],kind:'work'},
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
    NO_SCOPE:{stage:'scope',action:'SELECT_SCOPE',label:'Chọn sách và chương',title:'Chọn sách và chương',target:'scope',explanation:'Chọn một chương hoặc một phạm vi liên tiếp để bắt đầu.'},
    TEXT_BLOCKED:{stage:'text',action:'RESOLVE_TEXT',label:'Cần duyệt văn bản',title:'Cần duyệt văn bản',target:'text',explanation:'Duyệt bản văn đang dùng của chương này trước khi tiếp tục.'},
    SPEAKER_EXCEPTIONS:{stage:'speakers',action:'REVIEW_SPEAKERS',label:'Cần gán giọng',title:'Cần xác nhận người nói',target:'speakers',explanation:'Xác nhận những câu thoại còn chưa rõ người nói.'},
    VOICE_BLOCKED:{stage:'voices',action:'CONFIGURE_VOICES',label:'Cần gán giọng',title:'Cần gán giọng',target:'voices',explanation:'Chọn giọng đọc hợp lệ cho các vai còn thiếu.'},
    CASTING_REVIEW:{stage:'voice_map',action:'REVIEW_FINAL_VOICE_MAP',label:'Duyệt giọng',title:'Duyệt giọng',target:'voice_map',explanation:'Kiểm tra người nói và giọng được chọn, sau đó duyệt để tiếp tục.'},
    READY_TO_PREPARE:{stage:'prepare',action:'PREPARE',label:'Chuẩn bị',title:'Sẵn sàng chuẩn bị',target:'prepare',explanation:'Hệ thống sẽ cố định văn bản và giọng cho phạm vi đã chọn. Chưa gọi TTS.'},
    PREPARED:{stage:'render',action:'START_RENDER',label:'Bắt đầu render',title:'Sẵn sàng bắt đầu render',target:'render',explanation:'Đầu vào đã được ghim an toàn. Audio chỉ được tạo khi bạn bấm bắt đầu render.'},
    RENDERING_OR_PAUSED:{stage:'render',action:'MONITOR_OR_RESUME',label:'Theo dõi tiến độ',title:'Đang tạo audio',target:'render',explanation:'Audio đang được tạo hoặc đang chờ bạn tiếp tục.'},
    RENDERED_NOT_QA:{stage:'qa',action:'QA',label:'Cần nghe và duyệt',title:'Cần nghe và duyệt',target:'qa',explanation:'Audio đã tạo xong; hãy nghe trước khi hoàn tất chương.'},
    COMPLETE:{stage:'qa',action:'VIEW_OUTPUTS_OR_SELECT_NEXT_SCOPE',label:'Xem audio đã tạo',title:'Chương đã hoàn tất',target:'done',explanation:'Audio đã được nghe và chấp nhận.'},
    STATE_UNRESOLVED:{stage:'scope',action:'RELOAD_READ_ONLY',label:'Tải lại trạng thái',title:'Không xác định được trạng thái an toàn',target:'diagnostics',explanation:'Dữ liệu đọc được đang thiếu hoặc mâu thuẫn; chỉ hiển thị chẩn đoán/read-only.'},
  };
  const TASK_META={
    NO_SCOPE:{type:'SELECT_SCOPE',title:'Chọn sách và chương',summary:'Chọn một chương hoặc một phạm vi liên tiếp để bắt đầu.',action:'SELECT_SCOPE',label:'Chọn chương',target:'scope',next:'Ứng dụng sẽ mở việc đầu tiên trong phạm vi.'},
    TEXT_BLOCKED:{type:'REVIEW_TEXT',title:'Xác nhận nội dung',summary:'Đọc và duyệt bản văn đang dùng trước khi xác nhận người nói.',action:'REVIEW_TEXT',label:'Mở nội dung cần duyệt',target:'text',next:'Tiếp tục xác nhận người nói.'},
    SPEAKER_EXCEPTIONS:{type:'REVIEW_SPEAKER',title:'Xác nhận người nói',summary:'Xử lý từng câu chưa rõ người nói; các câu đã xác nhận được thu gọn.',action:'REVIEW_SPEAKER',label:'Xác nhận và tiếp tục',target:'speakers',next:'Tiếp tục câu chưa rõ tiếp theo hoặc chuyển sang gán giọng.'},
    VOICE_BLOCKED:{type:'EDIT_VOICE_ASSIGNMENTS',title:'Gán giọng',summary:'Chọn giọng cho narrator và các vai còn thiếu.',action:'EDIT_VOICE_ASSIGNMENTS',label:'Lưu bản nháp',target:'voices',next:'Mở màn hình duyệt giọng riêng.'},
    CASTING_REVIEW:{type:'REVIEW_VOICE_MAP',title:'Duyệt giọng',summary:'Kiểm tra giọng đã chọn và số câu bị ảnh hưởng trước khi duyệt.',action:'REVIEW_VOICE_MAP',label:'Duyệt và tiếp tục',target:'voice_map',next:'Phạm vi sẽ sẵn sàng để chuẩn bị.'},
    READY_TO_PREPARE:{type:'PREPARE_RANGE',title:'Chuẩn bị phạm vi',summary:'Cố định văn bản và giọng đã duyệt. Bước này không gọi TTS và không tạo audio.',action:'PREPARE_RANGE',label:'Chuẩn bị',target:'prepare',next:'Hiển thị bước Bắt đầu render riêng.'},
    PREPARED:{type:'START_RENDER',title:'Sẵn sàng render',summary:'Đầu vào đã được cố định và đang chờ lệnh bắt đầu riêng.',action:'START_RENDER',label:'Bắt đầu render',target:'render',next:'Theo dõi tiến độ tạo audio.'},
    RENDERING_OR_PAUSED:{type:'MONITOR_RENDER',title:'Đang tạo audio',summary:'Theo dõi tiến độ hoặc tiếp tục đúng phần bị lỗi.',action:'MONITOR_RENDER',label:'Xem tiến độ',target:'render',next:'Nghe và duyệt khi audio hoàn tất.'},
    RENDERED_NOT_QA:{type:'HUMAN_QA',title:'Nghe và duyệt',summary:'Nghe toàn bộ bản audio rồi chọn Cần sửa hoặc Chấp nhận.',action:null,label:'',target:'qa',next:'Mở output tiếp theo đang chờ duyệt.'},
    COMPLETE:{type:'COMPLETE',title:'Chương đã hoàn tất',summary:'Audio đã được nghe và chấp nhận.',action:'SELECT_NEXT_SCOPE',label:'Chọn phạm vi tiếp theo',target:'done',next:'Tải audio đã duyệt hoặc bắt đầu phạm vi sản xuất tiếp theo.'},
    STATE_UNRESOLVED:{type:'READ_ONLY_DIAGNOSTIC',title:'Cần kiểm tra trạng thái',summary:'Dữ liệu đọc được đang thiếu hoặc mâu thuẫn; chưa mở hành động thay đổi dữ liệu.',action:'RELOAD_READ_ONLY',label:'Tải lại trạng thái',target:'diagnostics',next:'Tiếp tục khi trạng thái đã rõ ràng.'},
  };
  function n(value){const num=Number(value);return Number.isFinite(num)?num:0}
  function lower(value){return String(value||'').toLowerCase()}
  function stageKeysBefore(stageKey){const index=STAGE_INDEX.get(stageKey)??0;return STAGES.slice(0,index).map(stage=>stage.key)}
  function phaseViewModel(conceptualState){
    const currentKey=STATE_PHASE[conceptualState]||'scope';
    const currentIndex=Math.max(0,PHASES.findIndex(phase=>phase.key===currentKey));
    const completeAll=conceptualState==='COMPLETE';
    const phases=PHASES.map((phase,index)=>({
      ...phase,
      current:index===currentIndex,
      complete:completeAll||index<currentIndex,
      locked:!completeAll&&index>currentIndex,
      state:index===currentIndex?'current':completeAll||index<currentIndex?'complete':'locked',
    }));
    return {
      currentPhaseKey:currentKey,
      currentPhaseNumber:currentIndex+1,
      currentPhaseLabel:PHASES[currentIndex].label,
      phases,
    };
  }
  function buildViewModel(conceptualState,overrides={}){
    const meta={...(STATE_META[conceptualState]||STATE_META.STATE_UNRESOLVED),...overrides};
    const task={...(TASK_META[conceptualState]||TASK_META.STATE_UNRESOLVED),...(overrides.task||{})};
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
    const phase=phaseViewModel(conceptualState);
    const primaryAction=task.action?{key:task.action,label:task.label,target:task.target,mutation:!!task.mutation}:null;
    const viewModel={
      conceptualState,
      currentStageKey,
      currentStageLabel:STAGES.find(stage=>stage.key===currentStageKey)?.label||currentStageKey,
      completedStageKeys,
      lockedStageKeys,
      primaryActionKey:primaryAction?.key||meta.action,
      primaryActionLabel:primaryAction?.label||meta.label,
      title:task.title||meta.title,
      explanation:task.summary||meta.explanation,
      blockerReason:meta.blockerReason||'',
      targetPanel:meta.target,
      mutationActionsMayBeDisplayed:MUTATION_STATES.has(conceptualState)&&!meta.readOnlyOnly,
      rangeReadinessAvailable:!!meta.rangeReadinessAvailable,
      diagnosticDetails:meta.diagnosticDetails||[],
      user_stage:phase.currentPhaseNumber,
      task_type:task.type,
      task_title:task.title,
      task_summary:task.summary,
      affected_chapter:overrides.affectedChapter||null,
      primary_action:primaryAction,
      secondary_links:overrides.secondaryLinks||[],
      blocker:meta.blockerReason||'',
      technical_details:meta.diagnosticDetails||[],
      next_task_after_success:task.next||'',
      queue:overrides.queue||[],
      stages,
      ...phase,
    };
    viewModel.stageSummaries=stageSummaries(viewModel);
    viewModel.panelStates=stagePanelStates(viewModel);
    return viewModel;
  }
  function stageSummaryText(stage,vm){
    if(stage.current)return vm.explanation||stage.summary;
    if(stage.complete)return 'Đã xong.';
    return 'Sau bước hiện tại.';
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
      const blockedNoScopeWorkspace=vm?.conceptualState==='NO_SCOPE'&&panel.id==='workspace';
      const active=panel.kind==='shell'||(!unresolved&&!blockedNoScopeRange&&!blockedNoScopeWorkspace&&panel.stages.includes(vm?.currentStageKey));
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
      return chapterNumber&&from<=chapterNumber&&to>=chapterNumber;
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
    const affectedChapter={
      id:n(input?.chapter?.id??input?.chapter_id)||null,
      number:n(input?.chapter?.chapter_number??input?.chapter_number)||null,
      title:input?.chapter?.title||'',
    };
    const jobs=scopedJobs(input);
    const liveJobs=jobs.filter(job=>PREPARED_JOB_STATUSES.has(lower(job.status))||ACTIVE_JOB_STATUSES.has(lower(job.status)));
    if(liveJobs.length>1)return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Có nhiều job active/resumable cho cùng một chương.',readOnlyOnly:true,diagnosticDetails:liveJobs.map(job=>`job:${job.id}:${job.status}`)});
    const recoverable=jobs.find(job=>job?.actions?.can_retry===true&&!job?.is_historical_output);
    const active=activeOutput(input);
    const hasOutput=!!(active.active_output_job_id||active.active_output_artifact_id||input?.audio_artifact?.id||input?.chapter?.active_audio_artifact_id);
    if(hasOutput&&!(active.active_output_artifact_id||input?.audio_artifact?.id||input?.chapter?.active_audio_artifact_id)){
      return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Active output có job nhưng thiếu artifact.',readOnlyOnly:true,diagnosticDetails:['active_output_missing_artifact']});
    }
    if(hasOutput){
      if(humanQaAccepted(input))return buildViewModel('COMPLETE',{affectedChapter,completedStageKeys:STAGES.map(stage=>stage.key)});
      return buildViewModel('RENDERED_NOT_QA',{affectedChapter});
    }
    if(liveJobs.length===1){
      const job=liveJobs[0],status=lower(job.status);
      if(PREPARED_JOB_STATUSES.has(status)){
        const missing=[];
        if(!n(job.casting_plan_id))missing.push('casting_plan_id');
        if(!n(job.from_chapter)||!n(job.to_chapter))missing.push('chapter_range');
        if(missing.length)return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Prepared job thiếu snapshot bắt buộc.',readOnlyOnly:true,diagnosticDetails:missing});
        return buildViewModel('PREPARED',{affectedChapter,diagnosticDetails:[`job:${job.id}`,`status:${job.status}`]});
      }
      const retry=job?.actions?.can_retry===true;
      return buildViewModel('RENDERING_OR_PAUSED',{affectedChapter,task:retry?{type:'RETRY_RENDER',title:'Render cần xử lý',summary:'Một phần audio gặp lỗi có thể thử lại mà không làm lại phần đã hoàn tất.',action:'RETRY_RENDER',label:'Thử lại phần lỗi',target:'render',next:'Tiếp tục theo dõi tiến độ render.'}:undefined,diagnosticDetails:[`job:${job.id}`,`status:${job.status}`]});
    }
    if(recoverable)return buildViewModel('RENDERING_OR_PAUSED',{affectedChapter,task:{type:'RETRY_RENDER',title:'Render cần xử lý',summary:'Một phần audio gặp lỗi có thể thử lại mà không làm lại phần đã hoàn tất.',action:'RETRY_RENDER',label:'Thử lại phần lỗi',target:'render',next:'Tiếp tục theo dõi tiến độ render.'},diagnosticDetails:[`job:${recoverable.id}`,`status:${recoverable.status}`]});
    if(TERMINAL_JOB_STATUSES.has(lower(input?.chapter?.audio_status))&&!hasOutput){
      return buildViewModel('STATE_UNRESOLVED',{blockerReason:'Trạng thái chương báo completed/terminal nhưng không có active output.',readOnlyOnly:true,diagnosticDetails:['terminal_without_output']});
    }
    if(!hasApprovedActiveText(input))return buildViewModel('TEXT_BLOCKED',{affectedChapter});
    const casting=input?.casting?.casting||input?.casting||{};
    const planStatus=lower(casting.status);
    if(casting.id&&planStatus==='approved'){
      const approvedVoiceReason=voiceBlocked(input);
      if(approvedVoiceReason)return buildViewModel('VOICE_BLOCKED',{affectedChapter,blockerReason:approvedVoiceReason});
      return buildViewModel('READY_TO_PREPARE',{affectedChapter});
    }
    const speakerReason=speakerBlocked(input);
    if(speakerReason){
      const draft=latestSpeakerDraft(input);
      const noDraft=!draft;
      const reviewComplete=!!draft&&!draft.stale&&lower(draft.status)!=='approved'&&n(draft.remaining_unreviewed_count)===0;
      const task=noDraft
        ?{type:'CREATE_SPEAKER_PROPOSAL',title:'Tạo đề xuất người nói',summary:'Hệ thống sẽ tạo một bản đề xuất để bạn xác nhận. Chưa gán giọng và chưa tạo audio.',action:'CREATE_SPEAKER_PROPOSAL',label:'Tạo đề xuất người nói',target:'speakers',next:'Mở câu chưa rõ đầu tiên để xác nhận.'}
        :reviewComplete
          ?{type:'CONFIRM_SPEAKER_REVIEW',title:'Hoàn tất xác nhận người nói',summary:'Tất cả câu cần xử lý đã có quyết định. Xác nhận để chuyển sang gán giọng.',action:'CONFIRM_SPEAKER_REVIEW',label:'Xác nhận và tiếp tục',target:'speakers',next:'Mở bước gán giọng.'}
          :undefined;
      return buildViewModel('SPEAKER_EXCEPTIONS',{affectedChapter,blockerReason:speakerReason,task});
    }
    if(!casting.id)return buildViewModel('VOICE_BLOCKED',{affectedChapter,task:{type:'CREATE_VOICE_MAP_DRAFT',title:'Gán giọng',summary:'Tạo bản nháp giọng từ các người nói đã xác nhận, sau đó kiểm tra từng lựa chọn ở màn hình riêng.',action:'CREATE_VOICE_MAP_DRAFT',label:'Lưu bản nháp',target:'voices',next:'Mở màn hình duyệt giọng riêng.'}});
    const voiceReason=voiceBlocked(input);
    if(voiceReason)return buildViewModel('VOICE_BLOCKED',{affectedChapter,blockerReason:voiceReason});
    if(planStatus==='draft')return buildViewModel('CASTING_REVIEW',{affectedChapter});
    if(planStatus!=='approved')return buildViewModel('STATE_UNRESOLVED',{blockerReason:`Casting Plan có trạng thái không hỗ trợ: ${casting.status}`,readOnlyOnly:true,diagnosticDetails:['unsupported_casting_status']});
    return buildViewModel('READY_TO_PREPARE',{affectedChapter});
  }
  function rangeBlockerText(state,item={}){
    const chapter=`Chương ${n(item.chapter_number)||'đang chọn'}`;
    const messages={
      STATE_UNRESOLVED:`${chapter} có trạng thái chưa xác định. Hãy mở chi tiết kỹ thuật và kiểm tra lại dữ liệu chương.`,
      TEXT_BLOCKED:`${chapter} cần duyệt văn bản. Hãy mở chương này và duyệt nội dung trước khi tiếp tục.`,
      SPEAKER_EXCEPTIONS:`${chapter} còn câu chưa rõ người nói. Hãy mở chương này để xác nhận người nói.`,
      VOICE_BLOCKED:`${chapter} chưa có giọng hợp lệ. Hãy mở Gán giọng và hoàn tất các vai còn thiếu.`,
      CASTING_REVIEW:`${chapter} cần duyệt phân vai. Hãy mở chương này và kiểm tra bản phân vai cuối.`,
      PREPARED:`${chapter} đã được chuẩn bị. Hãy mở Công việc khi bạn sẵn sàng bắt đầu render.`,
      RENDERING_OR_PAUSED:`${chapter} đang tạo audio hoặc tạm dừng. Hãy mở Công việc để theo dõi.`,
      RENDERED_NOT_QA:`${chapter} cần nghe và duyệt. Hãy mở Audio và hoàn tất kiểm tra chất lượng.`,
    };
    return messages[state]||`${chapter} cần xử lý. Hãy mở chương này để xem bước tiếp theo.`;
  }
  function resolveRangeProductionState(readiness,extra={}){
    const chapters=Array.isArray(readiness?.chapters)?readiness.chapters:[];
    if(!readiness?.scope||!chapters.length)return buildViewModel('NO_SCOPE',{rangeReadinessAvailable:true});
    const first=chapters.find(item=>String(item.state||'')!=='COMPLETE')||chapters[0];
    const current=String(first?.state||'STATE_UNRESOLVED');
    const rawBlocker=first?.blockers?.[0]||first?.message||'';
    const blocker=rangeBlockerText(current,first);
    const summary=readiness.summary||{};
    const detail=`${readiness.scope.book_title||'Sách'} · Chương ${readiness.scope.from_chapter}-${readiness.scope.to_chapter} · ${summary.needs_attention??0} cần xử lý.`;
    const count=n(readiness.scope.chapter_count)||chapters.length;
    const rangeTask=current==='READY_TO_PREPARE'?{label:`Chuẩn bị ${count} chương`}:current==='PREPARED'?{label:`Bắt đầu render ${count} chương`}:undefined;
    const queue=chapters.map((item,index)=>{
      const state=String(item.state||'STATE_UNRESOLVED');
      const userStage=(PHASES.findIndex(phase=>phase.key===(STATE_PHASE[state]||'scope'))+1)||1;
      const visual=state==='COMPLETE'?'complete':state==='STATE_UNRESOLVED'?'error':index===chapters.indexOf(first)?'current':item.requires_operator_action?'blocked':'pending';
      return {chapter_id:n(item.chapter_id)||null,chapter_number:n(item.chapter_number)||null,title:item.title||item.chapter_title||'',conceptual_state:state,user_stage:userStage,status:visual,requires_operator_action:!!item.requires_operator_action};
    });
    const overrides={rangeReadinessAvailable:true,affectedChapter:{id:n(first?.chapter_id)||null,number:n(first?.chapter_number)||null,title:first?.title||first?.chapter_title||''},task:rangeTask,queue,explanation:detail,blockerReason:['READY_TO_PREPARE','COMPLETE'].includes(current)?'':blocker,diagnosticDetails:[`range:${readiness.scope.from_chapter}-${readiness.scope.to_chapter}`,...(rawBlocker?[`backend:${rawBlocker}`]:[]),...chapters.filter(item=>item.requires_operator_action).map(item=>`chapter:${item.chapter_id}:${item.state}`)],...extra};
    if(current==='COMPLETE')return buildViewModel('COMPLETE',{...overrides,completedStageKeys:STAGES.map(stage=>stage.key)});
    return buildViewModel(current,overrides);
  }
  function productionScopeFromHash(hash){
    const raw=String(hash||'').replace(/^#/,'');
    const [path,query='']=raw.split('?');
    const route=path.replace(/^\//,'')||'home';
    const params=new URLSearchParams(query);
    const bookId=n(params.get('book'));
    const chapterId=n(params.get('chapter'));
    const inspectedChapterId=n(params.get('inspect'));
    const fromChapter=n(params.get('from'));
    const toChapter=n(params.get('to'));
    const skipCompleted=params.get('skip_completed')==='1';
    return {route,explicit:route==='production'&&(bookId||chapterId||fromChapter||toChapter),bookId:bookId||null,chapterId:chapterId||null,inspectedChapterId:inspectedChapterId||null,fromChapter:fromChapter||null,toChapter:toChapter||null,skipCompleted};
  }
  function productionHashForScope(scope){
    const bookId=n(scope?.bookId??scope?.book_id??scope?.book?.id);
    const chapterId=n(scope?.chapterId??scope?.chapter_id??scope?.chapter?.id);
    const inspectedChapterId=n(scope?.inspectedChapterId??scope?.inspected_chapter_id);
    const fromChapter=n(scope?.fromChapter??scope?.from_chapter);
    const toChapter=n(scope?.toChapter??scope?.to_chapter);
    if(!bookId||(!chapterId&&!fromChapter&&!toChapter))return '#/production';
    const params=new URLSearchParams({book:String(bookId)});
    if(fromChapter&&toChapter){params.set('from',String(fromChapter));params.set('to',String(toChapter))}
    if(chapterId&&!fromChapter&&!toChapter)params.set('chapter',String(chapterId));
    if(inspectedChapterId&&fromChapter&&toChapter)params.set('inspect',String(inspectedChapterId));
    if(scope?.skipCompleted)params.set('skip_completed','1');
    return `#/production?${params.toString()}`;
  }
  const api={STAGES,PHASES,STATE_PHASE,TASK_META,STAGE_PANEL_OWNERSHIP,resolveProductionState,resolveRangeProductionState,productionScopeFromHash,productionHashForScope,stagePanelStates};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.ProductionWorkflow=api;
})(typeof window!=='undefined'?window:globalThis);
