from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class OwnerRealUseAcceptanceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/'ui'/'index.html').read_text(encoding='utf-8')
        cls.js=(ROOT/'ui'/'app.js').read_text(encoding='utf-8')
        cls.doc=(ROOT/'docs'/'OWNER_REAL_USE_ACCEPTANCE.md').read_text(encoding='utf-8')

    def test_stage_4_review_is_native_and_primary_action_follows_context(self):
        task_pos=self.html.index('id="productionTaskContent"')
        action_pos=self.html.index('id="productionPrimaryActions"')
        self.assertLess(task_pos,action_pos)
        for token in ('ownerReviewTaskContent','Giọng sẽ dùng cho phạm vi này','Thông số TTS hiệu lực','Chuẩn bị tạo audio'):
            self.assertIn(token,self.js)
        self.assertIn("if(task==='PREPARE_RANGE')return ownerReviewTaskContent(vm)",self.js)

    def test_owner_journey_keeps_four_production_phases_and_audio_qa_separate(self):
        for token in ('Phạm vi','Nội dung & người nói','Nhân vật & giọng','Kiểm tra & tạo audio'):
            self.assertIn(token,self.js)
        self.assertIn('Giai đoạn ${stage} / 4',self.js)
        self.assertIn("audio:{hash:'#/audio',label:'Duyệt audio',heading:'Duyệt audio'}",self.js)
        self.assertIn('Audio đã được bàn giao sang Duyệt audio',self.js)
        self.assertNotIn('Nghe, sửa & hoàn tất',self.js)

    def test_prepare_and_start_render_are_distinct_owner_decisions(self):
        self.assertIn("if(task==='PREPARE_RANGE')",self.js)
        self.assertIn("if(['START_RENDER_RANGE','START_RENDER'].includes(task))",self.js)
        self.assertIn("primary.textContent='Chuẩn bị tạo audio'",self.js)
        self.assertIn("primary.textContent='Bắt đầu tạo audio'",self.js)
        self.assertIn('Snapshot này là bất biến.',self.js)

    def test_pre_render_acknowledgement_is_bound_to_scope_voice_and_tts_fingerprint(self):
        self.assertIn('function preRenderReviewFingerprint', self.js)
        self.assertIn('planFingerprint:String(technical.plan_fingerprint', self.js)
        self.assertIn('voiceIds,settings:{temperature:', self.js)
        self.assertIn('Đầu vào vừa thay đổi. Hãy kiểm tra lại bản đồ giọng và thông số TTS rồi xác nhận lại.', self.js)
        self.assertIn('bản đồ giọng và thông số TTS hiệu lực', self.js)
        self.assertIn('await loadProductionTaskProjection({silent:true})', self.js)

    def test_subset_of_existing_job_opens_owner_scope_without_starting_render(self):
        branch_start=self.js.index("if(action==='OPEN_JOB_RANGE')")
        branch_end=self.js.index("if(action==='START_RENDER_RANGE')", branch_start)
        branch=self.js[branch_start:branch_end]
        self.assertIn("await restoreProductionRangeScope({bookId,fromChapter:from,toChapter:to,skipCompleted:false})",branch)
        self.assertNotIn('startProductionRangeRender',branch)
        self.assertIn("if(task==='OPEN_JOB_RANGE')return'FOLLOW_JOB_SCOPE'",self.js)
        self.assertIn("OPEN_JOB_RANGE:'render'",self.js)
        self.assertIn("'PREPARE_RANGE','OPEN_JOB_RANGE','START_RENDER_RANGE'",self.js)

    def test_prepared_edit_reuses_guarded_cancel_and_requires_confirmation(self):
        self.assertIn('cancelPreparedForPreRenderEdit',self.js)
        self.assertIn('window.confirm',self.js)
        self.assertIn("api(`/api/jobs/${jobId}/cancel`,{method:'POST'})",self.js)
        self.assertIn("await openPreRenderConfigurationTarget('assignment')",self.js)
        self.assertNotIn('DELETE FROM jobs',self.js)

    def test_contextual_detours_reuse_existing_product_routes(self):
        self.assertIn("openCharacterReview()",self.js)
        self.assertIn("setAppRoute('voices')",self.js)
        self.assertIn("setAppRoute('assignment')",self.js)
        self.assertIn("rememberProductionWorkingContext",self.js)

    def test_next_cycle_resets_all_cycle_scoped_transient_state(self):
        self.assertIn('function resetProductionCycleTransientState()', self.js)
        for token in (
            "state.productionPreflight=null",
            "state.productionPrepare={readiness:null",
            "state.productionRepair={taskKey:null,mode:null,markers:[]}",
            "state.audioQa={history:[],loading:false,markers:[],activeArtifactId:null}",
            "state.audioLibrary.selectedArtifactId=null",
            "sessionStorage.removeItem(REPAIR_PLAN_OPEN_STORAGE_KEY)",
        ):
            self.assertIn(token, self.js)
        self.assertIn('resetProductionCycleTransientState();', self.js)

    def test_factory_reset_purges_orphaned_browser_context_after_books_load(self):
        self.assertIn('function reconcilePersistedBrowserContextWithBooks()',self.js)
        self.assertIn('reconcilePersistedBrowserContextWithBooks();const filtered=',self.js)
        self.assertIn('sessionStorage.removeItem(PRODUCTION_WORKING_CONTEXT_STORAGE_KEY)',self.js)
        self.assertIn('localStorage.removeItem(PRODUCTION_WORKING_CONTEXT_STORAGE_KEY)',self.js)
        self.assertIn('localStorage.removeItem(ASSIGNMENT_CONTEXT_STORAGE_KEY)',self.js)
        self.assertIn('localStorage.removeItem(PRODUCTION_RANGE_SCOPE_STORAGE_KEY)',self.js)
        self.assertIn('localStorage.removeItem(PRODUCTION_SCOPE_STORAGE_KEY)',self.js)
        self.assertIn("history.replaceState(null,'',cleanHash)",self.js)

    def test_contract_keeps_tts_knobs_truthful_and_product_complete_owner_gated(self):
        self.assertIn('Current product constraint: these values come from runtime Settings and are read-only.',self.doc)
        self.assertIn('No new persistence subsystem solely to make the currently fixed TTS knobs editable.',self.doc)
        self.assertIn('STORY_AUDIO_PRODUCT_COMPLETE',self.doc)
        self.assertIn('Owner completes at least one real chapter/range end-to-end',self.doc)

if __name__=='__main__':
    unittest.main()
