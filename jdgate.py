"""JD gate reader: flags ONLY explicit no-sponsorship / no-visa exclusions, returns the matched snippet for human reading.
'Must have the right to work' alone is NOT flagged (not an automatic future-sponsorship ban). Flag = needs a human read, never an auto-reject."""
import re
EXPLICIT = re.compile(r"(?:(?:we |company |employer )?(?:do(?:es)? not|don'?t|cannot|can'?t|unable to|not able to|will not|won'?t|are not (?:able|in a position) to)\s+(?:offer |provide |support |consider )?(?:visa )?sponsor\w*|no (?:visa )?sponsorship|sponsorship (?:is )?not (?:available|offered|provided)|not (?:offering|providing) (?:visa )?sponsorship|(?:applicants|candidates) (?:requiring|who require|that require|needing) (?:visa )?sponsorship (?:will )?(?:not be|cannot be|are not)\w* ?\w*|without (?:the )?(?:need|requirement) for (?:visa )?sponsorship|no work (?:permit|visa) (?:support|sponsorship))", re.I)
def gate(text):
    out = []
    for m in EXPLICIT.finditer(text or ''):
        a, b = max(0, m.start() - 80), min(len(text), m.end() + 80)
        out.append(' '.join(text[a:b].split()))
    return {'explicit_no_sponsorship_flag': bool(out), 'snippets': out[:3], 'state': 'FLAG_NEEDS_HUMAN_READ' if out else ('NO_EXPLICIT_EXCLUSION_FOUND' if text else 'NO_DESCRIPTION')}
