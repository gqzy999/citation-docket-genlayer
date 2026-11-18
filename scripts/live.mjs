import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdirSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { createAccount, createClient } from 'genlayer-js'
import { chain, checkNetwork, read, reader, waitFinalized } from '../src/chain.js'

const key = process.env.DOCKET_STUDIO_KEY
assert.match(key ?? '', /^0x[0-9a-f]{64}$/i, 'DOCKET_STUDIO_KEY must be an authorized Studionet signer')
const account = createAccount(key)
const client = createClient({chain, account})
const owner = account.address.toLowerCase()
const source = readFileSync('contracts/docket.py','utf8')
const slug = 'reference-release'
const ref = owner + '/' + slug
const filename = 'evidence/studionet.json'
mkdirSync('evidence',{recursive:true})
const data = existsSync(filename) ? JSON.parse(readFileSync(filename,'utf8')) : {
  chainId: 61999, owner, ref, sourceSha256: createHash('sha256').update(source).digest('hex'), steps: {},
}
assert.equal(data.owner,owner)
assert.equal(data.sourceSha256,createHash('sha256').update(source).digest('hex'))
const save = () => writeFileSync(filename,JSON.stringify(data,null,2)+'\n')

async function run(label, method, args, verify) {
  let step = data.steps[label]
  if (step?.readback) return step.readback
  if (!step) {
    await checkNetwork(client)
    data.steps[label] = step = {hash:null}
    save()
    step.hash = method === 'deploy'
      ? await client.deployContract({code:source,args:[],leaderOnly:false})
      : await client.writeContract({address:data.address,functionName:method,args,value:0n,leaderOnly:false})
    save()
  }
  assert(step.hash,'Uncertain broadcast. Check the chain before retrying.')
  console.log(label,step.hash)
  const tx = await waitFinalized(step.hash)
  assert.equal(tx.from_address.toLowerCase(),owner)
  const result = await verify(tx)
  Object.assign(step,{status:'FINALIZED',execution:'SUCCESS',readback:result})
  save()
  console.log(label,'FINALIZED / SUCCESS')
  return result
}

await run('deployment','deploy',[],async tx=>{
  const address=tx.data.contract_address
  assert.equal(await reader.getContractCode(address),source)
  data.address=address
  return {address,sourceVerified:true}
})
if(process.argv.includes('--deploy-only')) process.exit(0)
async function revision(num,state) {
  const result=await read(data.address,'get_version',[ref,num])
  assert.equal(result?.state,state)
  return result
}
await run('draft_1','revise',[slug,'Editorial references', '9500320,16144967',0],()=>revision(1,'DRAFT'))
const blocked=await run('screen_1','screen',[ref,1],()=>revision(1,'BLOCKED'))
assert.ok(blocked.findings.find(item=>item.pmid==='9500320').flags.includes('RETRACTED'))
await run('draft_2','revise',[slug,'Editorial references, revised', '16873767,16144967',1],()=>revision(2,'DRAFT'))
await run('screen_2','screen',[ref,2],()=>revision(2,'CHECKED'))
await run('publish_2','publish',[ref,2],async()=>{
  const result=await revision(2,'PUBLISHED')
  assert.equal((await read(data.address,'get_docket',[ref])).published,2)
  assert.equal((await revision(1,'BLOCKED')).state,'BLOCKED')
  return result
})
