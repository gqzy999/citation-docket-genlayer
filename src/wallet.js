import { createClient } from 'genlayer-js'
import { chain, rpc, explorer, checkNetwork } from './chain.js'

export async function switchNetwork(provider) {
  const chainId = '0xf22f'
  if (Number(await provider.request({method:'eth_chainId'})) === 61999) return
  try {
    await provider.request({method:'wallet_switchEthereumChain',params:[{chainId}]})
  } catch(error) {
    if (Number(error?.data?.originalError?.code ?? error.code) !== 4902) throw error
    await provider.request({method:'wallet_addEthereumChain',params:[{
      chainId, chainName:'GenLayer Stable Studionet', rpcUrls:[rpc], blockExplorerUrls:[explorer],
      nativeCurrency:{name:'GEN',symbol:'GEN',decimals:18},
    }]})
    if (Number(await provider.request({method:'eth_chainId'})) !== 61999) {
      await provider.request({method:'wallet_switchEthereumChain',params:[{chainId}]})
    }
  }
  if (Number(await provider.request({method:'eth_chainId'})) !== 61999) throw Error('Switch to Stable Studionet.')
}

export async function signer(provider, account) {
  if (!provider || !account) throw Error('Connect an injected wallet.')
  await switchNetwork(provider)
  const [active] = await provider.request({method:'eth_accounts'})
  if (active?.toLowerCase() !== account) throw Error('Wallet account changed. Reconnect before signing.')
  await checkNetwork()
  return createClient({chain, account, provider:{async request(request) {
    if (request.method === 'eth_sendTransaction') {
      if (Number(await provider.request({method:'eth_chainId'})) !== 61999) throw Error('Wallet network changed.')
      const [tx] = request.params
      if (BigInt(tx.value ?? 0) !== 0n || BigInt(tx.gasPrice ?? 1) !== 0n) throw Error('Expected a zero-value, zero-gas-price transaction.')
    }
    return provider.request(request)
  }}})
}
