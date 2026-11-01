"""把开发义务和 QA 用例的本地证据合并为只读交付就绪视图；不授予独立验收或发布权限。"""
from . import evidence, qa
from .project import Blocked


def _counts(items, excluded=False):
    return {
        'total': len(items),
        'passed': sum(item.get('status') == 'PASS' for item in items),
        'excluded': sum(item.get('status') == 'EXCLUDED' for item in items) if excluded else 0,
        'not_verified': sum(item.get('status') not in (('PASS', 'EXCLUDED') if excluded else ('PASS',))
                            for item in items),
    }


def evaluate(project):
    reasons = []
    dev_decision = dev_run = qa_result = qa_run = None
    try:
        dev_decision = evidence.decide(project)
        dev_run = evidence.load_current(project, 'dev')
    except (Blocked, OSError, ValueError, KeyError, TypeError, ImportError, StopIteration) as exc:
        reasons.append('DEVELOPMENT_EVIDENCE_UNAVAILABLE')
        dev_error = type(exc).__name__
    else:
        dev_error = None

    try:
        qa_result = qa.evaluate(project)
        qa_run = evidence.load_current(project, 'qa')
    except (Blocked, OSError, ValueError, KeyError, TypeError, ImportError, StopIteration) as exc:
        reasons.append('QA_EVIDENCE_UNAVAILABLE')
        qa_error = type(exc).__name__
    else:
        qa_error = None

    development_ok = False
    if dev_decision is not None and dev_run is not None:
        obligations = dev_decision.get('obligations', [])
        development_ok = (
            dev_decision.get('development') == 'DEV_VERIFIED_LOCAL'
            and dev_run.get('status') == 'PASS'
            and bool(obligations)
            and all(item.get('status') == 'PASS' for item in obligations)
        )
        if not development_ok:
            reasons.append('DEVELOPMENT_OBLIGATIONS_NOT_VERIFIED')
        binding = dev_decision.get('development_binding', {})
        if binding.get('status') != 'MATCHED':
            development_ok = False
            reasons.append('NATIVE_DEVELOPMENT_NOT_BOUND')

    qa_ok = False
    if qa_result is not None and qa_run is not None:
        cases = qa_result.get('cases', [])
        qa_ok = (
            qa_result.get('case_execution') == 'PASS_LOCAL'
            and qa_run.get('status') == 'PASS'
            and bool(cases)
            and all(item.get('status') in ('PASS', 'EXCLUDED') for item in cases)
            and any(item.get('status') == 'PASS' for item in cases)
        )
        if not qa_ok:
            reasons.append('QA_CASES_NOT_VERIFIED')

    same_subject = bool(
        dev_run is not None and qa_run is not None
        and dev_run.get('subject') == qa_run.get('subject')
        and dev_run.get('subject', {}).get('sha256') == qa_run.get('subject', {}).get('sha256')
    )
    if dev_run is not None and qa_run is not None and not same_subject:
        reasons.append('DEVELOPMENT_QA_SUBJECT_MISMATCH')

    ready = development_ok and qa_ok and same_subject
    dev_obligations = dev_decision.get('obligations', []) if dev_decision else []
    qa_cases = qa_result.get('cases', []) if qa_result else []
    return {
        'schema': 'ads-local-delivery-readiness/v1',
        # Local evidence is never promoted to an independent acceptance or release decision.
        'status': 'NOT_VERIFIED',
        'local_delivery_readiness': 'READY' if ready else 'BLOCKED',
        'reason_codes': sorted(set(reasons)),
        'development': {
            'status': dev_decision.get('development') if dev_decision else 'NOT_AVAILABLE',
            'run_id': dev_run.get('run_id') if dev_run else None,
            'subject_sha256': dev_run.get('subject', {}).get('sha256') if dev_run else None,
            'obligations': _counts(dev_obligations),
            'native_development_binding': dev_decision.get('development_binding', {}).get('status')
                if dev_decision else 'NOT_AVAILABLE',
            'error_type': dev_error,
        },
        'qa': {
            'case_execution': qa_result.get('case_execution') if qa_result else 'NOT_AVAILABLE',
            'run_id': qa_run.get('run_id') if qa_run else None,
            'subject_sha256': qa_run.get('subject', {}).get('sha256') if qa_run else None,
            'cases': _counts(qa_cases, excluded=True),
            'source_sha256': qa_result.get('source_sha256') if qa_result else None,
            'independence': 'NOT_VERIFIED',
            'qa_acceptance': 'NOT_GRANTED',
            'error_type': qa_error,
        },
        'subject_binding': {
            'same_exact_snapshot': same_subject,
            'status': 'MATCHED' if same_subject else 'NOT_VERIFIED',
        },
        'semantic_completeness': 'NOT_VERIFIED',
        'independent_qa_identity': 'NOT_VERIFIED',
        'release_authorization': 'NOT_GRANTED',
        'note': 'READY 仅表示本地开发义务与 QA 用例在同一项目快照上均有完整执行证据；不代表语义完备、独立 QA 验收、签名出处或发布授权。',
    }
