"""Validate public scout output before persistence; never trust bridge JSON."""
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

from ..graph import catalog
from .security import public_https_url

TYPES = {'documentation','docs','article','blog','video','paper','book','course','tutorial'}
STOP = {'with','from','that','this','tutorial','introduction','fundamentals','engineering','software','learning'}
_YT_ID_OK = re.compile(r'^[A-Za-z0-9_-]{11}$')


def _fake_youtube_id(host: str, path: str, query: str) -> bool:
    """Real YouTube video IDs are always exactly 11 chars from a fixed charset -- a fabricated
    placeholder (observed directly: 'example_video_id', after the scout agent failed to click
    through to a real result and gave up) is a syntactically fine-looking URL, so nothing else
    here would catch it. The same check already lives in bridges/mac_bridge.py, but this service's
    own docstring is "never trust bridge JSON" -- so it needs to hold here too, independently."""
    if host == 'youtu.be':
        return not _YT_ID_OK.match(path.lstrip('/').split('/')[0])
    if host.endswith('youtube.com') and path == '/watch':
        return not _YT_ID_OK.match(parse_qs(query).get('v', [''])[0])
    return False


def approved_topics(raw: list) -> list[str]:
    allowed = set(catalog.public_search_topics(list(catalog.concepts()), 10000))
    return list(dict.fromkeys(t for t in raw if isinstance(t,str) and t in allowed))[:12]


_FREE_TOPIC_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,.'&/()+:-]{2,119}$")


def sanitize_free_topics(raw: list) -> list[str]:
    """Pattern-based sanitizer for topics an LLM invented itself (no repository/graph backing
    them), as opposed to approved_topics()'s catalog allowlist, which only makes sense when a
    topic is meant to correspond 1:1 to a pre-vetted graph concept. A freshly-generated,
    no-repo-connected curriculum has no such catalog to check against, so this instead just
    guards against anything that looks like a URL, email, or code fragment rather than a plain
    public search phrase -- the same pattern already used for the browser-use bridge's own
    input sanitization."""
    out: list[str] = []
    for t in raw if isinstance(raw, list) else []:
        t = str(t).strip()
        if _FREE_TOPIC_OK.match(t) and '://' not in t and '@' not in t and t not in out:
            out.append(t)
        if len(out) >= 12:
            break
    return out


def validate_resources(resources, topics: list[str]) -> tuple[list[dict], int]:
    accepted, seen, rejected = [], set(), 0
    for r in resources[:60] if isinstance(resources,list) else []:
        try:
            if not isinstance(r,dict):raise ValueError()
            topic = r.get('topic')
            if topic not in topics:raise ValueError()
            title = str(r.get('title') or '').strip()
            why = str(r.get('why') or r.get('rationale') or '').strip()
            kind = r.get('resource_type') or r.get('type')
            if not 5 <= len(title) <= 240 or not 20 <= len(why) <= 1200 or kind not in TYPES:raise ValueError()
            url = public_https_url(str(r.get('url') or ''))
            parsed = urlsplit(url)
            if _fake_youtube_id(parsed.hostname or '',parsed.path,parsed.query):raise ValueError()
            url = urlunsplit((parsed.scheme,parsed.netloc.lower(),parsed.path,parsed.query,''))
            if len(url)>2000 or url in seen:raise ValueError()
            words = set(re.findall(r'[a-z0-9]+',topic.lower())) - STOP
            # why is included in the search text, not just title+URL: a genuinely relevant result
            # can easily be titled creatively enough to share no words with an abstractly-phrased
            # curriculum topic (e.g. topic "Building a small project using programming concepts"
            # matched to a real article titled "Very Deep Not Boring Beginner Projects" -- zero
            # literal overlap in title/URL, but the model's own why explanation says "...covering
            # various programming concepts..."), and that relevance explanation is exactly the
            # signal this check exists to catch when it's genuinely missing.
            matched = sorted(words & set(re.findall(r'[a-z0-9]+',(title+' '+why+' '+parsed.path).lower())))
            if not matched:raise ValueError()
            minutes = int(r.get('estimated_minutes') or 15)
            if not 1 <= minutes <= 600:raise ValueError()
            # Taken by the bridge in code (browser.take_screenshot()), never by the model itself --
            # size-capped defensively since it's untrusted bridge JSON like everything else here.
            shot = r.get('screenshot_base64')
            shot = shot if isinstance(shot,str) and 0 < len(shot) <= 3_000_000 else None
            seen.add(url)
            accepted.append({'url':url,'title':title,'topic':topic,'resource_type':kind,'source':parsed.hostname,
                             'why':why,'estimated_minutes':minutes,'screenshot_base64':shot,
                             'selection_evidence':{'topic':topic,'matched_terms':matched,'validation':'url_and_topic_lexical','semantic_review_required':True}})
        except (ValueError,TypeError,OverflowError):
            rejected += 1
    return accepted,rejected
