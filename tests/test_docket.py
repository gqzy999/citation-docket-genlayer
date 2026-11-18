import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch

OWNER = "0x" + "1" * 40


class DocketTest(unittest.TestCase):
    def setUp(self):
        def exposed(fn):
            return fn

        def consensus(leader, validate):
            result = leader()
            if not validate(result):
                raise ValueError("VALIDATORS_DISAGREE")
            return result

        self.message = SimpleNamespace(sender_address=OWNER)
        self.responses = []
        module = ModuleType("genlayer")
        module.TreeMap = dict
        module.u32 = int
        module.allow_storage = exposed
        module.gl = SimpleNamespace(
            Contract=object, message=self.message,
            public=SimpleNamespace(write=exposed, view=exposed),
            vm=SimpleNamespace(UserError=ValueError, unpack_result=exposed, run_nondet_unsafe=consensus),
            nondet=SimpleNamespace(web=SimpleNamespace(get=self.fetch)),
        )
        with patch.dict(sys.modules, {"genlayer":module}):
            scope = {}
            exec(Path("contracts/docket.py").read_text(), scope)
        self.contract = scope["CitationDocket"]()
        self.normalize = scope["normalize"]
        self.contract.dockets = {}
        self.contract.versions = {}
        self.ref = OWNER + "/release"
        self.contract.revise("release", "Editorial release", "9500320", 0)

    def fetch(self, url):
        return SimpleNamespace(status=200, body=json.dumps(self.responses.pop(0)).encode())

    def entry(self, pmid, *types):
        return {"result": {pmid: {"uid":pmid, "title":"Indexed citation", "pubtype":list(types)}}}

    def screen(self, version, payload):
        self.responses = [payload, payload]
        self.contract.screen(self.ref, version)

    def version(self, number):
        return json.loads(self.contract.get_version(self.ref, number))

    def test_blocked_revision_is_retained_after_replacement(self):
        self.screen(1, self.entry("9500320", "Retracted Publication"))
        with self.assertRaisesRegex(ValueError, "CURRENT_CHECKED"):
            self.contract.publish(self.ref, 1)
        self.contract.revise("release", "Replacement citation", "16144967", 1)
        self.screen(2, self.entry("16144967", "Journal Article"))
        self.contract.publish(self.ref, 2)
        self.assertEqual(self.version(1)["state"], "BLOCKED")
        self.assertEqual(self.version(2)["state"], "PUBLISHED")
        self.assertEqual(json.loads(self.contract.get_docket(self.ref))["published"], 2)

    def test_validator_disagreement_leaves_draft(self):
        self.responses = [self.entry("9500320","Journal Article"), self.entry("9500320","Retracted Publication")]
        with self.assertRaisesRegex(ValueError, "VALIDATORS_DISAGREE"):
            self.contract.screen(self.ref, 1)
        self.assertEqual(self.version(1)["state"], "DRAFT")

    def test_stale_edit_cannot_overwrite_revision(self):
        with self.assertRaisesRegex(ValueError, "STALE_REVISION"):
            self.contract.revise("release","Other draft","16144967",0)

    def test_unrelated_wallet_cannot_publish(self):
        self.screen(1, self.entry("9500320","Journal Article"))
        self.message.sender_address = "0x" + "2" * 40
        with self.assertRaisesRegex(ValueError, "OWNER_REQUIRED"):
            self.contract.publish(self.ref, 1)

    def test_missing_metadata_blocks_release(self):
        self.screen(1, {"result":{}})
        self.assertEqual(self.version(1)["findings"][0]["flags"], ["MISSING"])

    def test_superseded_draft_cannot_be_screened(self):
        self.contract.revise("release","New version","16144967",1)
        self.assertEqual(self.version(1)["state"],"SUPERSEDED")
        with self.assertRaisesRegex(ValueError, "CURRENT_DRAFT_REQUIRED"):
            self.contract.screen(self.ref,1)
