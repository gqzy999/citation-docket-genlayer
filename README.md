# Citation Docket

[Open Citation Docket](https://gqzy999.github.io/citation-docket-genlayer/) · [Stable Studionet contract](https://explorer-studio.genlayer.com/address/0x4D1bcD12BE74c19fE9aaa82f69d8f9271f130c37)

Citation Docket is an editorial release workspace for screening PubMed references. It records the exact citations an editor intended to release, preserves the evidence for blocked drafts, and lets readers compare those drafts with the released revision. A fresh screening requires a new revision, so later source changes leave earlier snapshots intact.

## Use the workspace

1. Open the published example to read both revisions without a wallet. The first revision includes PubMed record 9500320 and retains the retraction flag. The second revision uses replacement references.
2. Connect an injected EIP-1193 wallet on Stable Studionet (chain ID 61999). Create a docket with a short slug, a revision title and one to six unique PubMed IDs. The signing address owns the docket.
3. Screen the current draft with GenLayer. A blocked draft can be replaced through **New revision**. Reviewers can trigger a screening, and the owner controls revisions and publication.
4. Select **Publish revision** after screening returns **CHECKED**. Share the wallet/slug docket reference. Readers can open any revision and inspect its PubMed entries and status.

Publication releases the citation-screening record on chain. Journal publication, medical assessment, and content review remain with the editorial team.

## Contract

`DRAFT → BLOCKED` or `DRAFT → CHECKED → PUBLISHED`. A newer revision can supersede a draft or checked revision. Superseded, blocked and published revisions remain readable. The docket records the latest revision and the latest published revision separately.

Validators independently fetch the same [NCBI ESummary](https://www.ncbi.nlm.nih.gov/books/NBK25499/#chapter4.ESummary) batch and compare the normalized ordered vector of PubMed IDs, titles and flags. The screening policy blocks retracted publications, retraction notices, expressions of concern and missing records. A malformed response or inconsistent validator observations leave the draft retryable. The result reflects the configured PubMed publication types at screening time. PubMed indexing can lag publisher actions, corrections outside those types are outside scope, and a clean snapshot does not establish scientific validity.

## Run

Requires Node.js 22 and Python 3.

```sh
npm ci
npm test
npm run dev
npm run build
```

Set GitHub Pages to use GitHub Actions to publish the static build. The Svelte app uses EIP-6963 discovery and EIP-1193 wallet requests, and waits for successful finalization before reading chain state back.

For deployment and real-chain validation, supply a dedicated authorized Studionet signer in `DOCKET_STUDIO_KEY` and run `npm run live`. Add `-- --deploy-only` to stop after deployment. The script resumes known hashes from `evidence/studionet.json`. Use a fresh evidence path by moving the existing file outside the workspace before a separate validation run. The app's deployment address and example reference are set in `src/deployment.json`.

[Deployment and transaction evidence](evidence/studionet.json)

[Front-end transaction evidence](evidence/frontend.json) records a separate run of the production bundle. An EIP-1193 test adapter signs and submits real Studionet transactions. Native extension compatibility requires a browser with the corresponding wallet installed.

## Compare and share revisions

Open the published example and select **v2**. The comparison lists removed, retained and added PubMed IDs against v1 and includes the previous retraction flag. The example's screening receipt is linked separately from the human-readable table. **Copy revision link** opens the exact revision on a separate browser, and **Download evidence JSON** exports the chain reference, both revision snapshots and their differences.
