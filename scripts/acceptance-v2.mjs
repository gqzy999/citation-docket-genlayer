import assert from 'node:assert/strict'
import {chain,reader,checkNetwork,waitFinalized,read} from '../src/chain.js'
import {acceptance} from './acceptance-v2-support.mjs'

const {actors:[owner,screener],history,save,transaction,deploy}=acceptance({
  chain,reader,checkNetwork,waitFinalized,sourcePath:'contracts/docket.py',
})
await deploy()
const slug='editorial-release-v2'
const ref=owner.address+'/'+slug
const record=async(version,state)=>{
  const entry=await read(history.address,'get_version',[ref,version])
  assert.equal(entry.state,state)
  assert.equal(entry.revised_by,owner.address)
  return entry
}
await transaction('draft_1',0,'revise',[slug,'Editorial citations','20137807,9500320,16144967',0],()=>record(1,'DRAFT'))
const blocked=await transaction('screen_1',1,'screen',[ref,1],()=>record(1,'BLOCKED'))
assert.equal(blocked.screened_by,screener.address)
assert.ok(blocked.findings[0].flags.includes('NOTICE'))
assert.ok(blocked.findings[0].publication_types.includes('Retraction Notice'))
assert.ok(blocked.findings[1].flags.includes('RETRACTED'))
await transaction('blocked_publish',0,'publish',[ref,1],async()=>{
  const entry=await record(1,'BLOCKED')
  assert.deepEqual(entry,blocked)
  return entry
},'CURRENT_CHECKED_REVISION_REQUIRED')
await transaction('draft_2',0,'revise',[slug,'Revised editorial citations','16873767,16144967',1],()=>record(2,'DRAFT'))
const checked=await transaction('screen_2',1,'screen',[ref,2],()=>record(2,'CHECKED'))
await transaction('unauthorized_publish',1,'publish',[ref,2],async()=>{
  const entry=await record(2,'CHECKED')
  assert.deepEqual(entry,checked)
  return entry
},'OWNER_REQUIRED')
const published=await transaction('publish_2',0,'publish',[ref,2],async()=>{
  const entry=await record(2,'PUBLISHED')
  assert.deepEqual(await record(1,'BLOCKED'),blocked)
  assert.equal((await read(history.address,'get_docket',[ref])).published,2)
  return entry
})
assert.equal(published.published_by,owner.address)
history.ref=ref
save()
