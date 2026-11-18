# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
import re

API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id="
FLAGS = {
    "retracted publication": "RETRACTED",
    "retraction of publication": "NOTICE",
    "expression of concern": "CONCERN",
}


def normalize(payload, ids):
    results = payload.get("result")
    if not isinstance(results, dict):
        raise ValueError("PUBMED_RESPONSE_UNAVAILABLE")
    rows = []
    for pmid in ids:
        entry = results.get(pmid)
        if entry is None:
            rows.append(dict(pmid=pmid, title="", flags=["MISSING"]))
            continue
        types = entry.get("pubtype")
        title = entry.get("title")
        if entry.get("uid") != pmid or not isinstance(types, list) or not isinstance(title, str):
            raise ValueError("INVALID_PUBMED_ENTRY")
        if not title.strip() or not types or any(not isinstance(t, str) for t in types):
            raise ValueError("INVALID_PUBMED_ENTRY")
        flags = sorted({FLAGS[t.strip().lower()] for t in types if t.strip().lower() in FLAGS})
        rows.append(dict(pmid=pmid, title=" ".join(title.split())[:300], flags=flags))
    return rows


def citations(raw):
    ids = [item.strip() for item in raw.split(",")]
    if not 1 <= len(ids) <= 6 or len(set(ids)) != len(ids):
        raise ValueError("INVALID_CITATIONS")
    if any(not re.fullmatch(r"[1-9][0-9]{0,8}", pmid) for pmid in ids):
        raise ValueError("INVALID_CITATIONS")
    return ids


@allow_storage
class CitationDocket(gl.Contract):
    dockets: TreeMap[str, str]
    versions: TreeMap[str, str]

    def __init__(self):
        pass

    @gl.public.view
    def get_docket(self, key: str) -> str:
        return self.dockets.get(key, "")

    @gl.public.view
    def get_version(self, key: str, version: u32) -> str:
        return self.versions.get(key + "/" + str(version), "")

    @gl.public.write
    def revise(self, slug: str, title: str, pmids: str, previous: u32) -> None:
        owner = str(gl.message.sender_address).lower()
        key = owner + "/" + slug
        if not re.fullmatch(r"[a-z0-9-]{3,36}", slug) or not 3 <= len(title.strip()) <= 90:
            raise gl.vm.UserError("INVALID_DOCKET")
        try:
            ids = citations(pmids)
        except ValueError:
            raise gl.vm.UserError("INVALID_CITATIONS")
        docket = json.loads(self.dockets.get(key, "null"))
        latest = docket["latest"] if docket else 0
        if latest != int(previous):
            raise gl.vm.UserError("STALE_REVISION")
        if latest >= 100:
            raise gl.vm.UserError("REVISION_LIMIT")
        if docket is None:
            docket = dict(key=key, owner=owner, published=0, latest=0)
        if latest:
            last = json.loads(self.versions[key + "/" + str(latest)])
            if last["state"] in ("DRAFT", "CHECKED"):
                last["state"] = "SUPERSEDED"
                self.versions[key + "/" + str(latest)] = json.dumps(last)
        seq = latest + 1
        self.versions[key + "/" + str(seq)] = json.dumps(
            dict(version=seq, title=title.strip(), ids=ids, state="DRAFT", findings=[]))
        docket["latest"] = seq
        self.dockets[key] = json.dumps(docket)

    @gl.public.write
    def screen(self, key: str, version: u32) -> None:
        docket = json.loads(self.dockets.get(key, "null"))
        ref = key + "/" + str(version)
        revision = json.loads(self.versions.get(ref, "null"))
        if not docket or docket["latest"] != int(version) or not revision or revision["state"] != "DRAFT":
            raise gl.vm.UserError("CURRENT_DRAFT_REQUIRED")
        ids = revision["ids"]

        def retrieve():
            response = gl.nondet.web.get(API + ",".join(ids))
            if response.status != 200:
                return ""
            try:
                return json.dumps(normalize(json.loads(response.body), ids), sort_keys=True)
            except (ValueError, KeyError, TypeError):
                return ""

        def verify(leader):
            return gl.vm.unpack_result(leader) == retrieve()

        result = gl.vm.run_nondet_unsafe(retrieve, verify)
        if not result:
            raise gl.vm.UserError("PUBMED_RESPONSE_UNAVAILABLE")
        findings = json.loads(result)
        revision["findings"] = findings
        revision["state"] = "BLOCKED" if any(row["flags"] for row in findings) else "CHECKED"
        self.versions[ref] = json.dumps(revision)

    @gl.public.write
    def publish(self, key: str, version: u32) -> None:
        docket = json.loads(self.dockets.get(key, "null"))
        ref = key + "/" + str(version)
        revision = json.loads(self.versions.get(ref, "null"))
        if not docket or docket["owner"] != str(gl.message.sender_address).lower():
            raise gl.vm.UserError("OWNER_REQUIRED")
        if docket["latest"] != int(version) or not revision or revision["state"] != "CHECKED":
            raise gl.vm.UserError("CURRENT_CHECKED_REVISION_REQUIRED")
        revision["state"] = "PUBLISHED"
        docket["published"] = int(version)
        self.versions[ref] = json.dumps(revision)
        self.dockets[key] = json.dumps(docket)
