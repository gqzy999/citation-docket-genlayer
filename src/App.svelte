<script>
  import { onMount } from 'svelte'
  import { explorer, read, waitFinalized } from './chain.js'
  import { signer, switchNetwork } from './wallet.js'
  import deployment from './deployment.json'
  import example from '../evidence/studionet.json'
  import upgrade from '../evidence/v2.json'

  const params = new URLSearchParams(location.search)
  const legacy = example.address
  let contract = params.get('contract')===legacy || (!params.has('contract') && params.get('docket')===example.ref)
    ? legacy : deployment.address
  let sourceSteps = {}
  const reasons = {
    RETRACTED:'PubMed designates the original article as retracted.',
    NOTICE:'PubMed identifies this item as a retraction notice.',
    CONCERN:'PubMed indexes an expression of concern.',
    MISSING:'PubMed did not return a document summary for this PMID.',
  }
  let timeline = []
  let transactionIndex = {}
  try { transactionIndex=JSON.parse(localStorage.getItem('docket.receipts') ?? '{}') ?? {} } catch {}
  function receiptsFor(key, version) {
    const source = [example,upgrade].find(item=>item.address===contract && item.ref===key)
    return {...transactionIndex[contract+'/'+key+'/'+version],
      ...Object.fromEntries(['draft','screen','publish'].flatMap(method=>{
        const hash=source?.steps?.[method+'_'+version]?.hash
        return hash ? [[method,hash]] : []
      }))}
  }
  const refFormat = /^0x[0-9a-f]{40}\/[a-z0-9-]{3,36}$/
  const descriptions = {
    DRAFT:'Ready for independent PubMed screening.',
    CHECKED:'No configured PubMed flags found in this snapshot.',
    BLOCKED:'At least one citation requires editorial attention.',
    PUBLISHED:'This screening snapshot was released by the docket owner.',
    SUPERSEDED:'A newer revision replaced this draft.',
  }
  let mode = 'review'
  let reference = params.get('docket') || ''
  let docket = null
  let revision = null
  let recent = []
  let baseline = null
  let screeningHash = ''
  async function copyDocket() {
    const target = new URL(location.href)
    target.search = new URLSearchParams({contract,docket:docket.key,revision:String(revision.version)}).toString()
    await navigator.clipboard.writeText(target.href)
    message='Revision link copied'
  }
  let comparisonError = ''
  let changes = []
  $: changes = baseline && revision ? compare(baseline, revision) : []
  function compare(before, after) {
    const oldIds = new Set(before.ids)
    const newIds = new Set(after.ids)
    const index = new Map([...before.findings, ...after.findings].map(row => [row.pmid, row]))
    return [
      ...before.ids.filter(id => !newIds.has(id)).map(id => ({id, action:'Removed', row:index.get(id)})),
      ...after.ids.map(id => ({id, action:oldIds.has(id) ? 'Retained' : 'Added', row:index.get(id)})),
    ]
  }
  function exportRevision() {
    const packet = {chainId:61999,contract,docket,revision,receipts:sourceSteps,comparedWith:baseline,changes}
    const url = URL.createObjectURL(new Blob([JSON.stringify(packet,null,2)+'\n'],{type:'application/json'}))
    const link = document.createElement('a')
    link.href=url
    link.download=docket.key.split('/')[1]+'-v'+revision.version+'.json'
    link.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  let historyStart = 1
  let wallets = []
  let selected = ''
  let provider
  let account = ''
  let busy = false
  let message = 'Ready'
  let hash = ''
  let slug = ''
  let title = ''
  let ids = ''

  onMount(() => {
    const add = (name, candidate) => {
      if (!candidate?.request || wallets.some(wallet => wallet.provider === candidate)) return
      const id = String(wallets.length)
      wallets = [...wallets,{id,name,provider:candidate}]
      if (wallets.length === 1) selected = id
    }
    const announce = ({detail}) => add(detail.info.name, detail.provider)
    window.addEventListener('eip6963:announceProvider',announce)
    window.dispatchEvent(new Event('eip6963:requestProvider'))
    for (const candidate of [...(window.ethereum?.providers ?? [window.ethereum]),window.okxwallet,window.coinbaseWalletExtension]) {
      add(candidate?.isRabby ? 'Rabby' : candidate?.isOKExWallet ? 'OKX' :
        candidate?.isCoinbaseWallet ? 'Coinbase Wallet' : candidate?.isMetaMask ? 'MetaMask' : 'Injected wallet',candidate)
    }
    const number = Number(params.get('revision'))
    if (refFormat.test(reference)) act(() => load(reference,Number.isInteger(number) && number > 0 && number <= 100 ? number : undefined))
    return () => {
      window.removeEventListener('eip6963:announceProvider',announce)
      provider?.removeListener?.('accountsChanged',changed)
    }
  })

  function changed(list) { account = list[0]?.toLowerCase() ?? '' }
  function disconnect() {
    provider?.removeListener?.('accountsChanged',changed)
    provider = undefined
    account = ''
  }
  async function connect() {
    disconnect()
    const candidate = wallets.find(wallet=>wallet.id===selected)?.provider
    if (!candidate) throw Error('Enable an EIP-1193 browser wallet.')
    const list = await candidate.request({method:'eth_requestAccounts'})
    await switchNetwork(candidate)
    provider = candidate
    changed(list)
    provider.on?.('accountsChanged',changed)
    message = 'Connected to Stable Studionet'
  }

  async function act(action) {
    if (busy) return
    busy = true
    try { await action() }
    catch(error) { message=error.shortMessage ?? error.message ?? String(error) }
    finally { busy=false }
  }
  function begin(amend = false) {
    slug=amend ? docket.key.split('/')[1] : ''
    title=amend ? revision.title : ''
    ids=amend ? revision.ids.join(', ') : ''
    mode='compose'
  }
  async function load(key, version) {
    key=key.trim().toLowerCase()
    if (!refFormat.test(key)) throw Error('Enter a valid wallet/slug docket reference.')
    if (!contract) throw Error('Deployment address is unavailable.')
    const target=await read(contract,'get_docket',[key])
    if (!target) throw Error('No finalized docket for that reference.')
    const chosen=version ?? target.latest
    const entry=await read(contract,'get_version',[key,chosen])
    if (!entry) throw Error('Revision was not found.')
    docket=target
    revision=entry
    reference=key
    mode='review'
    historyStart=Math.max(1,chosen-3)
    recent=Array.from({length:Math.min(target.latest-historyStart+1,7)},(_,i)=>historyStart+i)
    sourceSteps=receiptsFor(key,chosen)
    screeningHash=sourceSteps.screen ?? ''
    timeline=[]
    if(contract!==legacy){
      try { timeline=await read(contract,'get_timeline',[key,historyStart,recent.length]) ?? [] } catch {}
    }
    timeline=recent.map(number=>timeline.find(item=>item.version===number) ??
      {version:number,state:number===chosen ? entry.state : undefined})
    baseline=null
    comparisonError=''
    if (chosen > 1) {
      try {
        baseline=await read(contract,'get_version',[key,chosen-1])
        if (!baseline) comparisonError='Earlier revision unavailable.'
      } catch {
        comparisonError='Earlier revision could not be loaded. Reopen this revision to retry.'
      }
    }
    message='Finalized revision loaded'
  }
  async function write(method,args,key,version,states) {
    if (!contract) throw Error('Deployment address is unavailable.')
    const client=await signer(provider,account)
    hash=''
    message='Approve the transaction in your wallet'
    hash=await client.writeContract({address:contract,functionName:method,args,value:0n,leaderOnly:false})
    await waitFinalized(hash,stage=>{message='Consensus · '+stage})
    const id=contract+'/'+key+'/'+version
    const operation=method==='revise'?'draft':method
    transactionIndex={...transactionIndex,[id]:{...transactionIndex[id],[operation]:hash}}
    try { localStorage.setItem('docket.receipts',JSON.stringify(transactionIndex)) } catch {}
    await load(key,version)
    if (!states.includes(revision.state)) throw Error('Finalized readback did not match the expected state.')
    message='FINALIZED / SUCCESS · '+revision.state
  }
  async function openExample(record) {
    if (!record.ref) throw Error('Example unavailable')
    const previous=contract
    contract=record.address
    try { await load(record.ref) }
    catch(error) { contract=previous; throw error }
  }
  async function saveDraft() {
    if (!account) throw Error('Connect a wallet before drafting.')
    const key=account+'/'+slug.trim().toLowerCase()
    if (!refFormat.test(key)) throw Error('Use 3–36 lowercase letters, digits or hyphens for the slug.')
    const prior=await read(contract,'get_docket',[key])
    const previous=prior?.latest ?? 0
    if (prior && (docket?.key!==key || docket.latest!==previous)) throw Error('Load the current docket and choose New revision.')
    await write('revise',[key.split('/')[1],title,ids,previous],key,previous+1,['DRAFT'])
  }
</script>

<div class="layout">
  <aside>
    <a class="wordmark" href="./"><span class="mark" aria-hidden="true">¶</span><span>Citation<br />Docket</span></a>
    <div class="nav">
      <button class:active={mode==='review'} onclick={() => mode='review'} disabled={busy}>Docket review</button>
      <button class:active={mode==='compose'} onclick={() => {if(contract!==deployment.address){docket=null;revision=null;baseline=null}contract=deployment.address;begin()}} disabled={busy || !account}>New docket</button>
    </div>
    <div class="rail-bottom"><span class="dot"></span> Stable Studionet <b>61999</b></div>
  </aside>
  <main>
    <header>
      <p>Editorial workspace · Stable Studionet 61999<br /><a href={explorer+'/address/'+contract} target="_blank" rel="noopener">Contract explorer ↗</a></p>
      <div class="wallet">
        <select aria-label="Injected wallet" bind:value={selected} onchange={disconnect} disabled={busy || !wallets.length}>
          {#if !wallets.length}<option value="">No injected wallet</option>{/if}
          {#each wallets as wallet}<option value={wallet.id}>{wallet.name}</option>{/each}
        </select>
        <button class="outline" onclick={() => act(connect)} disabled={busy || !wallets.length}>{account ? account.slice(0,6)+'…'+account.slice(-4) : 'Connect'}</button>
      </div>
    </header>
    <div class="workspace">
      <div class="status" role="status">{message}{#if hash} <a href={explorer+'/transactions/'+hash} target="_blank" rel="noopener">Transaction ↗</a>{/if}</div>
      {#if account}<p class="wallet-account">Connected account · {account}</p>{/if}
      {#if mode==='compose'}
        <h1>Draft a revision</h1>
        <p class="intro">Record the exact references that an editor plans to release. Your connected wallet will own this docket's revisions.</p>
        <form class="sheet draft" onsubmit={event=>{event.preventDefault();act(saveDraft)}}>
          <label>Docket slug<input bind:value={slug} required placeholder="editorial-references" /></label>
          <label>Revision title<input bind:value={title} required minlength="3" maxlength="90" placeholder="Reference list for the May issue" /></label>
          <label>PubMed IDs<textarea bind:value={ids} required rows="3" placeholder="One to six IDs, separated by commas"></textarea></label>
          <button class="primary" disabled={busy}>Record draft on chain</button>
        </form>
      {:else}
        <h1>Reference release</h1>
        <p class="intro">Screen a revision against PubMed before publishing its reference list.</p>
        <form class="lookup" onsubmit={event=>{event.preventDefault();act(()=>load(reference))}}>
          <label>Docket reference<input bind:value={reference} required placeholder="0x…/editorial-references" /></label>
          <button class="primary" disabled={busy}>Open docket</button>
          {#if deployment.ref}<button class="outline" type="button" onclick={()=>act(()=>openExample(upgrade.ref ? upgrade : example))} disabled={busy}>Open published example</button>{/if}
          {#if upgrade.ref}<button class="outline" type="button" onclick={()=>act(()=>openExample(example))} disabled={busy}>Open historical example</button>{/if}
        </form>
        {#if docket && revision}
          <section class="sheet" aria-label="Revision details">
            <div class="sheet-head"><div><span class="caption">Latest revision {docket.latest} · Released {docket.published || '—'} · {revision.ids.length} references</span><h2>{revision.title}</h2></div><span class="badge" class:flagged={revision.state==='BLOCKED'}>{revision.state}</span></div>
            <nav aria-label="Revisions">
              {#if historyStart>1}<button onclick={()=>act(()=>load(docket.key,historyStart-1))} disabled={busy}>Earlier</button>{/if}
              {#each timeline as item}<button class:chosen={revision.version===item.version} onclick={()=>act(()=>load(docket.key,item.version))} disabled={busy}>v{item.version} {item.state ?? ''}</button>{/each}
              {#if recent.at(-1)<docket.latest}<button onclick={()=>act(()=>load(docket.key,docket.latest))} disabled={busy}>Latest</button>{/if}
            </nav>
            <div class="table-wrap">
              <table><thead><tr><th scope="col">PMID</th><th scope="col">Citation</th><th scope="col">PubMed screening</th></tr></thead><tbody>
                {#each revision.ids as id,i}
                  {@const row=revision.findings[i]}
                  <tr><td><a href={'https://pubmed.ncbi.nlm.nih.gov/'+id+'/'} target="_blank" rel="noopener">{id} ↗</a></td><td>{row?.title || '—'}<small class="types">{row?.publication_types?.join(' · ') || (row?'Publication types unavailable in this record':'')}</small></td><td class:warn={row?.flags.length}>{row ? row.flags.join(', ') || 'No configured flag' : 'Awaiting check'}{#each row?.flags ?? [] as flag}<small class="types">{reasons[flag]}</small>{/each}</td></tr>
                {/each}
              </tbody></table>
            </div>
            <section class="change-panel" aria-label="Responsibility and evidence">
              <h3>Responsibility and evidence</h3>
              <p>{contract===legacy ? 'This historical contract compared ordered PMIDs, titles and risk flags.' : 'Validators read NCBI ESummary independently and compare the ordered PMIDs, titles, publication types and risk flags.'}</p>
              <p><a href={'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id='+revision.ids.join(',')} target="_blank" rel="noopener">Current NCBI ESummary metadata ↗</a></p>
              <dl class="responsibility">
                {#each [['Docket owner',docket.owner,''],['Revised by',revision.revised_by,'draft'],['Screened by',revision.screened_by,'screen'],['Published by',revision.published_by,'publish']] as [label,actor,method]}
                  <div><dt>{label}</dt><dd>{actor ?? '—'} {#if sourceSteps[method]}<a href={explorer+'/transactions/'+sourceSteps[method]} target="_blank" rel="noopener">Transaction ↗</a>{/if}</dd></div>
                {/each}
              </dl>
            </section>
            {#if baseline}
              <section class="change-panel" aria-label="Changes from previous revision">
                <div class="change-head"><div><span class="caption">VERSION COMPARISON</span><h3>What changed from v{baseline.version} to v{revision.version}</h3></div><button class="outline" onclick={exportRevision} disabled={busy}>Download evidence JSON</button></div>
                <ul class="change-list">
                  {#each changes as item (item.id)}
                    <li><span class="change-tag" class:removed={item.action==='Removed'} class:added={item.action==='Added'}>{item.action}</span>
                      <div><a href={'https://pubmed.ncbi.nlm.nih.gov/'+item.id+'/'} target="_blank" rel="noopener">PMID {item.id} ↗</a><p>{item.row?.title || 'Title not captured in this revision'}</p></div>
                      {#if item.row?.flags.length}<strong class="change-flag">{item.row.flags.join(', ')}</strong>{/if}
                    </li>
                  {/each}
                </ul>
              </section>
            {:else if comparisonError}
              <p class="change-panel">{comparisonError}</p>
            {/if}
            <div class="sheet-foot"><div><p>{descriptions[revision.state]}</p>{#if screeningHash}<a href={explorer+'/transactions/'+screeningHash} target="_blank" rel="noopener">View screening receipt ↗</a>{/if}</div>
              <p>{revision.state==='DRAFT'?'Any connected wallet can screen this draft. A flagged citation blocks publication.':revision.state==='CHECKED'?'Only the docket owner can publish this checked revision.':''}</p>
              <div class="sheet-actions">
                <button class="outline" onclick={()=>act(copyDocket)} disabled={busy}>Copy revision link</button>
                {#if !baseline}<button class="outline" onclick={exportRevision} disabled={busy}>Download evidence JSON</button>{/if}
                {#if contract!==legacy && account && revision.version===docket.latest && revision.state==='DRAFT'}<button class="primary" disabled={busy} onclick={()=>act(()=>write('screen',[docket.key,revision.version],docket.key,revision.version,['BLOCKED','CHECKED']))}>Screen with GenLayer</button>{/if}
                {#if contract!==legacy && account===docket.owner && revision.version===docket.latest}
                  {#if revision.state==='CHECKED'}<button class="primary" disabled={busy} onclick={()=>act(()=>write('publish',[docket.key,revision.version],docket.key,revision.version,['PUBLISHED']))}>Publish revision</button>{/if}
                  <button class="outline" disabled={busy} onclick={()=>begin(true)}>New revision</button>
                {/if}
              </div>
            </div>
          </section>
        {:else}
          <section class="empty"><span aria-hidden="true">¶</span><h2>Open a docket to see its revisions</h2><p>Each screening snapshot includes the PubMed records behind the release decision.</p></section>
        {/if}
      {/if}
      <footer>PubMed metadata screening · Editorial decisions remain with the publishing team.</footer>
    </div>
  </main>
</div>
