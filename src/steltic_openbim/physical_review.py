"""Conservative physical-data screens; these do not repair or approve a design."""
from .bim_contract import physical_screens


def review_physical(physical):
    findings=physical_screens(physical)
    return dict(status='needs_review' if findings else 'no_findings_in_limited_screens',
                structural_design_approval=False,findings=findings,
                limits=['Checks screen explicit section-count labels, opening host bounds and remote connection box parts.',
                        'These checks do not establish capacity, architectural agreement, complete framing, physical fit or constructability.',
                        'Source geometry is retained unchanged. Findings require source-model review; export remains available.'])
