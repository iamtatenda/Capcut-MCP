#!/usr/bin/env node
/* eslint-disable */
/**
 * capcut-upload.mjs — 零依赖的 CapCut 媒资上传脚本（Node 版）
 *
 * 支持两类上传，均先经 MCP capcut_asset_upload_credential 拿凭证，再由本脚本完成上传：
 *   - 视频      -> VOD（火山点播 / CapCut AI Search-tiktok 网关）
 *   - 图片      -> ImageX（火山图片处理服务）
 * 音频上传暂不支持。
 *
 * 从浏览器 SDK packages/tt-uploader 抽取核心逻辑重写而成，去除所有浏览器依赖：
 *   - XMLHttpRequest      -> node:https
 *   - File/Blob/FileReader-> node:fs
 *   - crypto-js 签名       -> node:crypto（火山 V4 签名，等价实现）
 *   - Worker/localStorage/tea 日志 -> 移除
 *
 * VOD 上传链路（与 SDK 完全一致）：
 *   分片: crc32 -> apply(ApplyUploadInfo) -> init -> upload(分片) -> merge -> commit(CommitUploadInfo)
 *   直传: crc32 -> apply(ApplyUploadInfo) -> upload(整包)          -> commit(CommitUploadInfo)
 * ImageX 上传链路（对齐 tt-uploader image 分支）：
 *   直传: crc32 -> apply(ApplyImageUpload) -> upload(整包)         -> commit(CommitImageUpload)
 *   分片: crc32 -> apply(ApplyImageUpload) -> init -> upload(分片) -> merge -> commit(CommitImageUpload)
 *   ImageX 与 VOD 数据面、CRC32、签名(signV4 火山变体)完全共用，仅 Action/Version/域名/收发结构不同。
 *
 * 数据面（init/分片/merge/直传）使用服务端下发的 Auth 令牌，控制面（apply/commit）由本脚本 V4 签名。
 *
 * 用法：
 *   # 视频 -> VOD
 *   node scripts/capcut-upload.mjs --file ./a.mp4 --client-id video-1 --upload-session-stdin --json
 *   # 图片 -> ImageX
 *   node scripts/capcut-upload.mjs --file ./a.png --client-id image-1 --upload-session-stdin --json
 *   # 视频和图片混合批量上传
 *   node scripts/capcut-upload.mjs \
 *     --files '[{"client_id":"video-1","file":"./a.mp4"},{"client_id":"image-1","file":"./cover.png"}]' \
 *     --upload-session-stdin --json
 *
 * 鉴权：通过 --upload-session 或 --upload-session-stdin 整段传入
 * capcut_asset_upload_credential 返回的短期凭证响应，不接受拆分凭证、永久 AK/SK
 * 或手工拼装的 STS 凭证。自动化环境优先使用 stdin，避免凭证出现在进程参数中。
 *
 * 成功时（--json）向 stdout 输出：VOD 为 { success:true, vid, setPublic, result }，
 * ImageX 为 { success:true, uri, result }；失败输出 { success:false, ... } 并以非 0 退出。
 */

import fs from 'node:fs'
import path from 'node:path'
import https from 'node:https'
import crypto from 'node:crypto'
import { URL } from 'node:url'

// ------------------------------ 常量 ------------------------------
const VOD_DOMAIN = {
  'cn-north-1': 'https://vod.volcengineapi.com',
  'ap-southeast-1': 'https://vod.ap-southeast-1.volcengineapi.com',
}
const DEFAULT_REGION = 'cn-north-1'
const VOD_SERVICE = 'vod'
const VOD_VERSION = '2022-01-01'
const M = 1024 * 1024
// 当前支持的视频和图片扩展名，与服务端素材类型白名单保持一致。
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'm4v', 'mkv', 'webm', 'avi', 'mpeg', 'mpg', '3gp', 'ts', 'mts', 'm2ts'])
const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'avif', 'svg'])

// ------------------------------ ImageX 常量（对齐 tt-uploader image 分支）------------------------------
// 控制面（ApplyImageUpload/CommitImageUpload）与 VOD volc 一样走火山 HMAC-SHA256 变体（signV4），
// 仅 service 名不同：imagex（小写）。数据面（直传/分片）与 VOD volc 完全共用。
const IMAGEX_SERVICE = 'imagex'
const IMAGEX_VERSION = '2018-08-01'
// 各区 ImageX OpenAPI 域名（凭证不带控制面域名时按服务端签发的 region 选择）。
const IMAGEX_DOMAIN = {
  'cn-north-1': 'https://imagex.volcengineapi.com',
  'ap-southeast-1': 'https://imagex.ap-southeast-1.volcengineapi.com',
}

// ------------------------------ CRC32 ------------------------------
const CRC_TABLE = (() => {
  const table = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[n] = c
  }
  return table
})()

/**
 * Formats a CRC32 number as an eight-character hexadecimal string.
 */
function toEight(hex) {
  while (hex.length < 8) hex = `0${hex}`
  return hex
}

/** 计算 buffer 的 crc32，返回 8 位十六进制字符串（与 SDK lib/crc32 一致） */
function computeCrc32(buf) {
  const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let crc = -1
  for (let i = 0; i < u8.length; i++) {
    crc = CRC_TABLE[(crc ^ u8[i]) & 0xff] ^ (crc >>> 8)
  }
  return toEight(((crc ^ -1) >>> 0).toString(16))
}

// ------------------------------ 火山 V4 签名 ------------------------------
const UNSIGNABLE_HEADERS = [
  'authorization',
  'content-type',
  'content-length',
  'user-agent',
  'presigned-expires',
  'expect',
  'x-amzn-trace-id',
]

/**
 * Escapes a string for canonical signed URI and query components.
 */
function uriEscape(str) {
  return encodeURIComponent(str)
    .replace(/[^A-Za-z0-9_.~\-%]+/g, escape)
    .replace(/[*]/g, (ch) => `%${ch.charCodeAt(0).toString(16).toUpperCase()}`)
}

/** 与 SDK signers/queryParamsToString 保持一致：按 key 排序、逐项转义 */
function queryParamsToString(params) {
  return Object.keys(params)
    .sort()
    .map((key) => {
      const val = params[key]
      if (val === undefined || val === null) return
      const escapedKey = uriEscape(key)
      if (!escapedKey) return
      if (Array.isArray(val)) {
        return `${escapedKey}=${val.map(uriEscape).sort().join(`&${escapedKey}=`)}`
      }
      return `${escapedKey}=${uriEscape(String(val))}`
    })
    .filter((v) => v)
    .join('&')
}

/**
 * Creates an HMAC-SHA256 digest for signing requests.
 */
function hmac(key, data) {
  return crypto.createHmac('sha256', key).update(data, 'utf8').digest()
}

/**
 * Computes a lowercase SHA256 hex digest for the provided data.
 */
function sha256hex(data) {
  return crypto.createHash('sha256').update(data, 'utf8').digest('hex')
}

/**
 * Reports whether a header should be included in the canonical signature.
 */
function isSignableHeader(key) {
  const lower = key.toLowerCase()
  if (lower.indexOf('x-amz-') === 0) return true
  return UNSIGNABLE_HEADERS.indexOf(lower) < 0
}

/**
 * 火山 V4 签名，等价于 SDK AWSSignersV4（isVolcengine:true）。
 * @returns {{ Authorization:string, 'X-Date':string, [k:string]:string }} 需要追加到请求上的头
 */
function signV4({ method, params, headers, body, region, service, credentials, date }) {
  const dateHeader = 'X-Date'
  const tokenHeader = 'x-security-token'
  const contentSha256Header = 'X-Content-Sha256'
  const algorithm = 'HMAC-SHA256'

  const iso = date.toISOString().replace(/\.\d{3}Z$/, 'Z')
  const datetime = iso.replace(/[:-]|\.\d{3}/g, '')
  const date8 = datetime.substr(0, 8)

  const signHeaders = { ...headers, [dateHeader]: datetime }
  if (credentials.sessionToken) signHeaders[tokenHeader] = credentials.sessionToken
  if (body) signHeaders[contentSha256Header] = sha256hex(body)

  // canonical headers（signable、按 key 小写排序）
  const entries = Object.keys(signHeaders)
    .map((k) => [k, signHeaders[k]])
    .filter(([k]) => isSignableHeader(k))
    .sort((a, b) => (a[0].toLowerCase() < b[0].toLowerCase() ? -1 : 1))
  const canonicalHeaders = entries
    .map(([k, v]) => `${k.toLowerCase()}:${String(v).replace(/\s+/g, ' ').replace(/^\s+|\s+$/g, '')}`)
    .join('\n')
  const signedHeaders = entries.map(([k]) => k.toLowerCase()).sort().join(';')

  const bodyHash = signHeaders[contentSha256Header] || sha256hex(body || '')
  const canonicalString = [
    method.toUpperCase(),
    '/',
    queryParamsToString(params || {}),
    `${canonicalHeaders}\n`,
    signedHeaders,
    bodyHash,
  ].join('\n')

  const credScope = [date8, region, service, 'request'].join('/')
  const stringToSign = [algorithm, datetime, credScope, sha256hex(canonicalString)].join('\n')

  const kDate = hmac(credentials.secretAccessKey, date8)
  const kRegion = hmac(kDate, region)
  const kService = hmac(kRegion, service)
  const kSigning = hmac(kService, 'request')
  const signature = crypto.createHmac('sha256', kSigning).update(stringToSign, 'utf8').digest('hex')

  const authorization =
    `${algorithm} Credential=${credentials.accessKeyId}/${credScope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`

  const out = { Authorization: authorization, [dateHeader]: datetime }
  if (credentials.sessionToken) out[tokenHeader] = credentials.sessionToken
  if (signHeaders[contentSha256Header]) out[contentSha256Header] = signHeaders[contentSha256Header]
  return out
}

/**
 * AWS4-HMAC-SHA256 签名（CapCut AI Search / tiktok VOD 内部网关 inner 协议使用）。
 * 与火山 volc 变体（signV4）的关键差异（经官方 @byted/ttuploader 抓包逐字节对齐）：
 *   - 算法/头名：AWS4-HMAC-SHA256、x-amz-date、x-amz-security-token（volc 是 HMAC-SHA256、X-Date、x-security-token）
 *   - 签名密钥前缀 'AWS4' + secret，scope 尾段 aws4_request（volc 无前缀、尾段 request）
 *   - GET 不签 body；POST 追加 x-amz-content-sha256 并纳入 SignedHeaders
 * canonQuery 同时用于签名与拼接实际 URL，确保二者逐字节一致。
 * @returns {{ authorization:string, canonQuery:string, headers:object }}
 */
function signAWS4({ method, params, body, region, service, credentials, date }) {
  const p = (n) => String(n).padStart(2, '0')
  const amzDate =
    `${date.getUTCFullYear()}${p(date.getUTCMonth() + 1)}${p(date.getUTCDate())}` +
    `T${p(date.getUTCHours())}${p(date.getUTCMinutes())}${p(date.getUTCSeconds())}Z`
  const dateStamp = amzDate.slice(0, 8)

  const payloadHash = sha256hex(body || '')
  const headers = { 'x-amz-date': amzDate }
  if (credentials.sessionToken) headers['x-amz-security-token'] = credentials.sessionToken
  if (body != null) headers['x-amz-content-sha256'] = payloadHash

  const hkeys = Object.keys(headers).sort()
  const canonicalHeaders = hkeys.map((k) => `${k}:${headers[k]}\n`).join('')
  const signedHeaders = hkeys.join(';')

  const canonQuery = Object.keys(params)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]))}`)
    .join('&')

  const canonicalRequest = [method.toUpperCase(), '/', canonQuery, canonicalHeaders, signedHeaders, payloadHash].join('\n')
  const scope = `${dateStamp}/${region}/${service}/aws4_request`
  const stringToSign = ['AWS4-HMAC-SHA256', amzDate, scope, sha256hex(canonicalRequest)].join('\n')

  let k = hmac('AWS4' + credentials.secretAccessKey, dateStamp)
  k = hmac(k, region)
  k = hmac(k, service)
  k = hmac(k, 'aws4_request')
  const signature = crypto.createHmac('sha256', k).update(stringToSign, 'utf8').digest('hex')

  const authorization =
    `AWS4-HMAC-SHA256 Credential=${credentials.accessKeyId}/${scope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`
  return { authorization, canonQuery, headers: { ...headers, authorization } }
}

// ------------------------------ HTTP（node:https） ------------------------------
function request({ method = 'GET', url, headers = {}, body, timeout = 5 * 60 * 1000 }) {
  return new Promise((resolve, reject) => {
    const u = new URL(url)
    const opts = {
      method,
      hostname: u.hostname,
      port: u.port || 443,
      path: `${u.pathname}${u.search}`,
      headers,
      timeout,
    }
    const req = https.request(opts, (res) => {
      const chunks = []
      res.on('data', (c) => chunks.push(c))
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }))
    })
    req.on('error', (err) => reject(new Error(`NETERROR: ${err.message} @ ${url}`)))
    req.on('timeout', () => {
      req.destroy(new Error(`TIMEOUT @ ${url}`))
    })
    if (body !== undefined && body !== null) req.write(body)
    req.end()
  })
}

async function requestWithRetry(opts, { retry = 2, interval = 2000, label = '', retryStatus = false } = {}) {
  let lastErr
  for (let i = 0; i <= retry; i++) {
    try {
      const response = await request(opts)
      if (retryStatus && (response.status === 408 || response.status === 425 || response.status === 429 || response.status >= 500)) {
        throw new Error(`HTTP ${response.status}`)
      }
      return response
    } catch (err) {
      lastErr = err
      if (i < retry) {
        log(`${label} 失败，${interval}ms 后重试 (${i + 1}/${retry}): ${err.message}`)
        await sleep(interval)
      }
    }
  }
  throw lastErr
}

// ------------------------------ 视频上传完成 ------------------------------
async function finalizeVideo(cfg, vid) {
  const body = JSON.stringify({ vid })
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    'Content-Length': Buffer.byteLength(body),
    Authorization: `Bearer ${cfg.finalizeToken}`,
  }

  const res = await requestWithRetry(
    { method: 'POST', url: cfg.finalizeURL, headers, body, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: '完成视频上传', retryStatus: true },
  )
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`finalize HTTP ${res.status}`)
  }
  let payload
  try {
    payload = JSON.parse(res.body)
  } catch {
    throw new Error('finalize 响应无法解析')
  }
  if (payload?.status !== 'success' || payload?.vid !== vid) {
    throw new Error(`finalize 失败: ${payload?.error || 'unexpected response'}`)
  }
  return payload
}

// ------------------------------ 工具 ------------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function log(...args) {
  process.stderr.write(`[capcut-upload] ${args.join(' ')}\n`)
}

function resolveUri(uri) {
  if (!uri) return ''
  const first = uri.split('/')[0]
  const rest = uri.split('/').slice(1).join('/')
  return `${first}/${encodeURIComponent(rest)}`
}

function resolveHeader(hd, { gatewayUpload = false } = {}) {
  const ret = {}
  if (gatewayUpload) ret['x-storage-mode'] = 'gateway'
  if (Array.isArray(hd)) {
    hd.forEach((item) => {
      if (item.Key && item.Value) ret[String(item.Key).toLowerCase()] = item.Value
    })
    return ret
  }
  if (hd && typeof hd === 'object') return Object.assign(ret, hd)
  return ret
}

function getSliceSize(size) {
  if (size <= 200 * M) return 5 * M
  if (size <= 500 * M) return 8 * M
  return 10 * M
}

function buildSlices(fileSize, sliceSize) {
  const slices = []
  let start = 0
  let end = 0
  while (end < fileSize) {
    end = Math.min(start + sliceSize, fileSize)
    if (fileSize - end <= sliceSize) end = fileSize
    slices.push({ start, end })
    start = end
  }
  return slices
}

function readSlice(fd, start, end) {
  const length = end - start
  const buf = Buffer.allocUnsafe(length)
  let read = 0
  while (read < length) {
    const n = fs.readSync(fd, buf, read, length - read, start + read)
    if (n <= 0) break
    read += n
  }
  return read === length ? buf : buf.subarray(0, read)
}

function getFileSuffix(fileName) {
  if (!fileName) return null
  const pos = fileName.lastIndexOf('.')
  return pos > 0 ? `.${fileName.substring(pos + 1)}` : null
}

function getSignDate(cfg, extraMs = 0) {
  if (cfg.useServerCurrentTime && cfg.credentials.currentTime) {
    return new Date(new Date(cfg.credentials.currentTime).getTime() + extraMs)
  }
  return new Date()
}

function assertVodResponse(bodyStr, stage) {
  let parsed
  try {
    parsed = JSON.parse(bodyStr)
  } catch (e) {
    throw new Error(`[${stage}] 解析响应失败: ${e.message}; body=${bodyStr.slice(0, 500)}`)
  }
  const err = parsed?.ResponseMetadata?.Error
  if (err) {
    throw new Error(`[${stage}] ${err.Code}(${err.CodeN}): ${err.Message}; RequestId=${parsed.ResponseMetadata.RequestId}`)
  }
  return parsed.Result
}

function assertTransporterResponse(bodyStr, status, stage) {
  if (status < 200 || status >= 300) {
    throw new Error(`[${stage}] HTTP ${status}: ${bodyStr.slice(0, 500)}`)
  }
  let parsed
  try {
    parsed = JSON.parse(bodyStr)
  } catch (e) {
    return null
  }
  if (parsed.success !== 0 && parsed.success !== undefined) {
    const e = parsed.error || {}
    throw new Error(`[${stage}] ${e.error_code}: ${e.message || bodyStr.slice(0, 300)}`)
  }
  return parsed.payload
}

async function applyUpload(cfg) {
  const host = cfg.videoHost || VOD_DOMAIN[cfg.region] || VOD_DOMAIN[DEFAULT_REGION]
  const params = {
    Action: 'ApplyUploadInfo',
    Version: VOD_VERSION,
    SpaceName: cfg.spaceName,
    FileSize: cfg.fileSize,
    FileType: cfg.fileType,
    NeedFallback: true,
  }
  if (cfg.fileName) params.FileName = cfg.fileName
  const ext = cfg.fileExtension || (cfg.useFileExtension ? getFileSuffix(cfg.fileName || cfg.baseName) : null)
  if (ext) params.FileExtension = ext
  if (cfg.storageClass !== undefined && cfg.storageClass !== null) params.StorageClass = cfg.storageClass
  if (cfg.accountId) params['X-Account-Id'] = cfg.accountId
  params.s = Math.random().toString(36).substr(2)

  const signed = signV4({
    method: 'GET',
    params,
    headers: {},
    region: cfg.region,
    service: VOD_SERVICE,
    credentials: cfg.credentials,
    date: getSignDate(cfg),
  })
  const url = `${host}?${queryParamsToString(params)}`
  const res = await requestWithRetry(
    { method: 'GET', url, headers: signed, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'apply' },
  )
  const result = assertVodResponse(res.body, 'apply')
  const detail =
    result?.Data?.CandidateUploadAddresses?.MainUploadAddresses?.[0] ?? result?.Data?.UploadAddress
  if (!detail) throw new Error(`[apply] 返回缺少上传地址: ${JSON.stringify(result).slice(0, 500)}`)
  const store = detail.StoreInfos[0]
  return {
    oid: resolveUri(store.StoreUri),
    signature: store.Auth,
    tosDomain: `${cfg.schema}://${detail.UploadHosts[0]}`,
    sessionKey: detail.SessionKey,
    serverUploadHeader: detail.UploadHeader,
  }
}

async function initUpload(cfg, ctx) {
  const url = `${ctx.tosDomain}/${ctx.oid}?uploads`
  const res = await requestWithRetry(
    {
      method: 'POST',
      url,
      headers: { authorization: ctx.signature, ...ctx.uploadHeader },
      timeout: cfg.requestTimeout,
    },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'init' },
  )
  const payload = assertTransporterResponse(res.body, res.status, 'init')
  const uploadId = payload?.uploadID
  if (!uploadId) throw new Error(`[init] 未获取到 uploadID: ${res.body.slice(0, 300)}`)
  return uploadId
}

async function uploadChunk(cfg, ctx, { url, buffer, crc32 }) {
  const headers = {
    authorization: ctx.signature,
    'content-crc32': crc32,
    'Content-Type': 'application/octet-stream',
    'Content-Length': String(buffer.length),
    ...ctx.uploadHeader,
  }
  const res = await requestWithRetry(
    { method: 'POST', url, headers, body: buffer, timeout: cfg.uploadTimeout },
    { retry: cfg.retryUploadTime, interval: cfg.retryInterval, label: 'upload' },
  )
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`[upload] HTTP ${res.status}: ${res.body.slice(0, 300)}`)
  }
}

async function mergeUpload(cfg, ctx, crc32List) {
  const content = crc32List.map((crc32, i) => `${i + 1}:${crc32}`).join(',')
  const url = `${ctx.tosDomain}/${ctx.oid}?uploadID=${ctx.uploadId}`
  const res = await requestWithRetry(
    {
      method: 'POST',
      url,
      headers: { authorization: ctx.signature, ...ctx.uploadHeader },
      body: content,
      timeout: cfg.requestTimeout,
    },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'merge' },
  )
  assertTransporterResponse(res.body, res.status, 'merge')
}

async function commitUpload(cfg, ctx, uploadDurationMs = 0) {
  const host = cfg.videoHost || VOD_DOMAIN[cfg.region] || VOD_DOMAIN[DEFAULT_REGION]
  const params = {
    Action: 'CommitUploadInfo',
    Version: VOD_VERSION,
    SpaceName: cfg.spaceName,
  }
  if (cfg.accountId) params['X-Account-Id'] = cfg.accountId
  const bodyObj = { SessionKey: ctx.sessionKey }
  if (Array.isArray(cfg.processAction) && cfg.processAction.length > 0) bodyObj.Functions = cfg.processAction
  if (cfg.callbackArgs) bodyObj.CallbackArgs = cfg.callbackArgs
  if (cfg.expireTime) bodyObj.ExpireTime = cfg.expireTime

  const urlBody = Object.keys(bodyObj)
    .map((key) => {
      const value = bodyObj[key]
      const tag = Object.prototype.toString.call(value)
      if (tag === '[object Array]' || tag === '[object Object]') {
        return `${key}=${encodeURIComponent(JSON.stringify(value))}`
      }
      return `${key}=${encodeURIComponent(value)}`
    })
    .join('&')

  const signed = signV4({
    method: 'POST',
    params,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: urlBody,
    region: cfg.region,
    service: VOD_SERVICE,
    credentials: cfg.credentials,
    date: getSignDate(cfg, uploadDurationMs),
  })
  const url = `${host}?${queryParamsToString(params)}`
  const res = await requestWithRetry(
    {
      method: 'POST',
      url,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...signed },
      body: urlBody,
      timeout: cfg.requestTimeout,
    },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'commit' },
  )
  const result = assertVodResponse(res.body, 'commit')
  return result?.Data
}

// ------------------------------ ImageX 协议（图片上传）------------------------------
async function applyImageUpload(cfg) {
  const isInner = cfg.imagexProtocol === 'inner'
  const host = isInner ? cfg.imagexHost : cfg.imagexHost || IMAGEX_DOMAIN[cfg.region] || IMAGEX_DOMAIN[DEFAULT_REGION]
  const params = {
    Action: 'ApplyImageUpload',
    Version: IMAGEX_VERSION,
    ServiceId: cfg.imageServiceId,
    UploadNum: 1,
  }
  const ext = cfg.fileExtension || (cfg.useFileExtension ? getFileSuffix(cfg.fileName || cfg.baseName) : null)
  if (ext) params.FileExtension = ext
  if (cfg.storeKey) params.StoreKeys = cfg.storeKey
  if (cfg.accountId) params['X-Account-Id'] = cfg.accountId
  params.s = Math.random().toString(36).substr(2)

  let url
  let headers
  if (isInner) {
    const signed = signAWS4({
      method: 'GET',
      params,
      region: cfg.region,
      service: IMAGEX_SERVICE,
      credentials: cfg.credentials,
      date: getSignDate(cfg),
    })
    url = `${host}?${signed.canonQuery}`
    headers = signed.headers
  } else {
    const signed = signV4({
      method: 'GET',
      params,
      headers: {},
      region: cfg.region,
      service: IMAGEX_SERVICE,
      credentials: cfg.credentials,
      date: getSignDate(cfg),
    })
    url = `${host}?${queryParamsToString(params)}`
    headers = signed
  }
  const res = await requestWithRetry(
    { method: 'GET', url, headers, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'apply(imagex)' },
  )
  const result = assertVodResponse(res.body, 'apply(imagex)')
  const detail = result?.UploadAddress
  const store = detail?.StoreInfos?.[0]
  if (!store) throw new Error(`[apply(imagex)] 返回缺少上传地址: ${JSON.stringify(result).slice(0, 500)}`)
  return {
    storeUri: store.StoreUri,
    oid: resolveUri(store.StoreUri),
    signature: store.Auth,
    tosDomain: `${cfg.schema}://${detail.UploadHosts[0]}`,
    sessionKey: detail.SessionKey,
    serverUploadHeader: detail.UploadHeader,
  }
}

async function commitImageUpload(cfg, ctx, uploadDurationMs = 0) {
  const isInner = cfg.imagexProtocol === 'inner'
  const host = isInner ? cfg.imagexHost : cfg.imagexHost || IMAGEX_DOMAIN[cfg.region] || IMAGEX_DOMAIN[DEFAULT_REGION]
  const params = {
    Action: 'CommitImageUpload',
    Version: IMAGEX_VERSION,
    ServiceId: cfg.imageServiceId,
  }
  if (cfg.skipMeta) params.SkipMeta = true
  if (cfg.accountId) params['X-Account-Id'] = cfg.accountId

  const bodyObj = { SessionKey: ctx.sessionKey, SuccessOids: [ctx.storeUri] }
  if (Array.isArray(cfg.processAction) && cfg.processAction.length > 0) bodyObj.Functions = cfg.processAction
  const body = JSON.stringify(bodyObj)

  let url
  let headers
  if (isInner) {
    const signed = signAWS4({
      method: 'POST',
      params,
      body,
      region: cfg.region,
      service: IMAGEX_SERVICE,
      credentials: cfg.credentials,
      date: getSignDate(cfg, uploadDurationMs),
    })
    url = `${host}?${signed.canonQuery}`
    headers = { ...signed.headers, 'Content-Type': 'application/json' }
  } else {
    const signed = signV4({
      method: 'POST',
      params,
      headers: { 'Content-Type': 'application/json' },
      body,
      region: cfg.region,
      service: IMAGEX_SERVICE,
      credentials: cfg.credentials,
      date: getSignDate(cfg, uploadDurationMs),
    })
    url = `${host}?${queryParamsToString(params)}`
    headers = { 'Content-Type': 'application/json', ...signed }
  }
  const res = await requestWithRetry(
    { method: 'POST', url, headers, body, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'commit(imagex)' },
  )
  const result = assertVodResponse(res.body, 'commit(imagex)')
  return result?.Results?.[0]
}

async function uploadImage(cfg) {
  const stat = fs.statSync(cfg.file)
  if (!stat.isFile()) throw new Error(`不是有效文件: ${cfg.file}`)
  cfg.fileSize = stat.size
  cfg.baseName = path.basename(cfg.file)
  const sliceSize = cfg.sliceSize || getSliceSize(cfg.fileSize)
  const isDirect = cfg.fileSize < sliceSize * 2

  log(`[imagex] 文件: ${cfg.baseName} (${cfg.fileSize} bytes), 模式: ${isDirect ? '直传' : '分片'}, 分片大小: ${sliceSize}`)

  log('阶段 apply(ApplyImageUpload)...')
  const applied = await applyImageUpload(cfg)
  const ctx = {
    storeUri: applied.storeUri,
    oid: applied.oid,
    signature: applied.signature,
    tosDomain: applied.tosDomain,
    sessionKey: applied.sessionKey,
    uploadHeader: resolveHeader(applied.serverUploadHeader, { gatewayUpload: !isDirect }),
  }
  log(`apply(imagex) 成功 oid=${ctx.oid}`)

  const fd = fs.openSync(cfg.file, 'r')
  const uploadStart = Date.now()
  try {
    if (isDirect) {
      const buffer = readSlice(fd, 0, cfg.fileSize)
      const crc32 = computeCrc32(buffer)
      log('阶段 upload(直传整包)...')
      await uploadChunk(cfg, ctx, { url: `${ctx.tosDomain}/${ctx.oid}`, buffer, crc32 })
    } else {
      log('阶段 init...')
      ctx.uploadId = await initUpload(cfg, ctx)
      log(`init 成功 uploadId=${ctx.uploadId}`)

      const slices = buildSlices(cfg.fileSize, sliceSize)
      const crc32List = new Array(slices.length)
      const parallel = Math.max(1, Math.min(cfg.uploadSliceCount, slices.length))
      log(`阶段 upload: 共 ${slices.length} 片, 并发 ${parallel}...`)

      let next = 0
      let done = 0
      const worker = async () => {
        while (next < slices.length) {
          const idx = next++
          const { start, end } = slices[idx]
          const buffer = readSlice(fd, start, end)
          const crc32 = computeCrc32(buffer)
          crc32List[idx] = crc32
          const url = `${ctx.tosDomain}/${ctx.oid}?partNumber=${idx + 1}&uploadID=${ctx.uploadId}`
          await uploadChunk(cfg, ctx, { url, buffer, crc32 })
          done++
          log(`分片 ${idx + 1}/${slices.length} 完成 (${Math.round((done / slices.length) * 100)}%)`)
        }
      }
      await Promise.all(Array.from({ length: parallel }, () => worker()))

      log('阶段 merge...')
      await mergeUpload(cfg, ctx, crc32List)
      log('merge 成功')
    }
  } finally {
    fs.closeSync(fd)
  }
  const uploadDurationMs = Date.now() - uploadStart

  log('阶段 commit(CommitImageUpload)...')
  const data = await commitImageUpload(cfg, ctx, uploadDurationMs)
  log('commit(imagex) 成功')
  return data
}

// ------------------------------ Inner 协议（CapCut AI Search / tiktok VOD 网关） ------------------------------
const INNER_VERSION = '2020-11-19'
const INNER_SLICE = 3 * M

async function applyUploadInner(cfg) {
  const host = cfg.videoHost
  const params = {
    Action: 'ApplyUploadInner',
    Version: INNER_VERSION,
    SpaceName: cfg.spaceName,
    FileType: cfg.fileType,
    IsInner: '1',
    FileSize: String(cfg.fileSize),
  }
  if (cfg.accountId) params['X-Account-Id'] = cfg.accountId

  const { canonQuery, headers } = signAWS4({
    method: 'GET',
    params,
    region: cfg.region,
    service: VOD_SERVICE,
    credentials: cfg.credentials,
    date: getSignDate(cfg),
  })
  const url = `${host}?${canonQuery}`
  const res = await requestWithRetry(
    { method: 'GET', url, headers, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'apply(inner)' },
  )
  const result = assertVodResponse(res.body, 'apply(inner)')
  const node = result?.InnerUploadAddress?.UploadNodes?.[0]
  const store = node?.StoreInfos?.[0]
  if (!node || !store) throw new Error(`[apply(inner)] 返回缺少上传节点: ${JSON.stringify(result).slice(0, 500)}`)
  return {
    uploadHost: node.UploadHost,
    storeUri: store.StoreUri,
    auth: store.Auth,
    sessionKey: node.SessionKey,
    userU: crypto.randomUUID(),
  }
}

async function initUploadInner(cfg, ctx) {
  const url = `${cfg.schema}://${ctx.uploadHost}/upload/v1/${ctx.storeUri}?uploadmode=part&phase=init`
  const res = await requestWithRetry(
    { method: 'POST', url, headers: { authorization: ctx.auth, 'x-storage-u': ctx.userU }, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'init(inner)' },
  )
  const parsed = JSON.parse(res.body)
  if (parsed.code !== 2000) throw new Error(`[init(inner)] ${parsed.message || res.body.slice(0, 300)}`)
  return parsed.data.uploadid
}

async function transferChunkInner(cfg, ctx, { partNumber, partOffset, buffer, crc32 }) {
  const q = `uploadid=${ctx.uploadId}&part_number=${partNumber}&phase=transfer&part_offset=${partOffset}`
  const url = `${cfg.schema}://${ctx.uploadHost}/upload/v1/${ctx.storeUri}?${q}`
  const headers = {
    authorization: ctx.auth,
    'x-storage-u': ctx.userU,
    'content-crc32': crc32,
    'content-type': 'application/octet-stream',
    'content-disposition': 'attachment; filename="undefined"',
    'Content-Length': String(buffer.length),
  }
  const res = await requestWithRetry(
    { method: 'POST', url, headers, body: buffer, timeout: cfg.uploadTimeout },
    { retry: cfg.retryUploadTime, interval: cfg.retryInterval, label: 'transfer(inner)' },
  )
  const parsed = JSON.parse(res.body)
  if (parsed.code !== 2000) throw new Error(`[transfer(inner)] part ${partNumber}: ${parsed.message || res.body.slice(0, 300)}`)
}

async function finishUploadInner(cfg, ctx, crc32List) {
  const body = crc32List.map((crc32, i) => `${i + 1}:${crc32}`).join(',')
  const url = `${cfg.schema}://${ctx.uploadHost}/upload/v1/${ctx.storeUri}?uploadmode=part&phase=finish&uploadid=${ctx.uploadId}&size=${cfg.fileSize}`
  const res = await requestWithRetry(
    { method: 'POST', url, headers: { authorization: ctx.auth, 'x-storage-u': ctx.userU }, body, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'finish(inner)' },
  )
  const parsed = JSON.parse(res.body)
  if (parsed.code !== 2000) throw new Error(`[finish(inner)] ${parsed.message || res.body.slice(0, 300)}`)
}

async function commitUploadInner(cfg, ctx, uploadDurationMs = 0) {
  const host = cfg.videoHost
  const params = { Action: 'CommitUploadInner', Version: INNER_VERSION, SpaceName: cfg.spaceName }
  if (cfg.accountId) params['X-Account-Id'] = cfg.accountId
  const bodyObj = { SessionKey: ctx.sessionKey }
  if (Array.isArray(cfg.processAction) && cfg.processAction.length > 0) bodyObj.Functions = cfg.processAction
  if (cfg.callbackArgs) bodyObj.CallbackArgs = cfg.callbackArgs
  if (cfg.expireTime) bodyObj.ExpireTime = cfg.expireTime
  const body = JSON.stringify(bodyObj)

  const { canonQuery, headers } = signAWS4({
    method: 'POST',
    params,
    body,
    region: cfg.region,
    service: VOD_SERVICE,
    credentials: cfg.credentials,
    date: getSignDate(cfg, uploadDurationMs),
  })
  const url = `${host}?${canonQuery}`
  const res = await requestWithRetry(
    { method: 'POST', url, headers: { ...headers, 'content-type': 'application/json' }, body, timeout: cfg.requestTimeout },
    { retry: cfg.retryTaskTime, interval: cfg.retryInterval, label: 'commit(inner)' },
  )
  const result = assertVodResponse(res.body, 'commit(inner)')
  return result?.Results?.[0]
}

async function uploadInner(cfg) {
  const stat = fs.statSync(cfg.file)
  if (!stat.isFile()) throw new Error(`不是有效文件: ${cfg.file}`)
  cfg.fileSize = stat.size
  cfg.baseName = path.basename(cfg.file)
  const sliceSize = cfg.sliceSize || INNER_SLICE
  log(`[inner] 文件: ${cfg.baseName} (${cfg.fileSize} bytes), 分片大小: ${sliceSize}`)

  log('阶段 apply(ApplyUploadInner)...')
  const applied = await applyUploadInner(cfg)
  const ctx = { ...applied }
  log(`apply(inner) 成功 host=${ctx.uploadHost} uri=${ctx.storeUri}`)

  const fd = fs.openSync(cfg.file, 'r')
  const uploadStart = Date.now()
  try {
    log('阶段 init...')
    ctx.uploadId = await initUploadInner(cfg, ctx)
    log(`init 成功 uploadid=${ctx.uploadId}`)

    const slices = buildSlices(cfg.fileSize, sliceSize)
    const crc32List = new Array(slices.length)
    const parallel = Math.max(1, Math.min(cfg.uploadSliceCount, slices.length))
    log(`阶段 transfer: 共 ${slices.length} 片, 并发 ${parallel}...`)

    let next = 0
    let done = 0
    const worker = async () => {
      while (next < slices.length) {
        const idx = next++
        const { start, end } = slices[idx]
        const buffer = readSlice(fd, start, end)
        const crc32 = computeCrc32(buffer)
        crc32List[idx] = crc32
        await transferChunkInner(cfg, ctx, { partNumber: idx + 1, partOffset: start, buffer, crc32 })
        done++
        log(`分片 ${idx + 1}/${slices.length} 完成 (${Math.round((done / slices.length) * 100)}%)`)
      }
    }
    await Promise.all(Array.from({ length: parallel }, () => worker()))

    log('阶段 finish...')
    await finishUploadInner(cfg, ctx, crc32List)
    log('finish 成功')
  } finally {
    fs.closeSync(fd)
  }
  const uploadDurationMs = Date.now() - uploadStart

  log('阶段 commit(CommitUploadInner)...')
  const data = await commitUploadInner(cfg, ctx, uploadDurationMs)
  log('commit(inner) 成功')
  return data
}

// ------------------------------ 主流程 ------------------------------
async function upload(cfg) {
  const stat = fs.statSync(cfg.file)
  if (!stat.isFile()) throw new Error(`不是有效文件: ${cfg.file}`)
  cfg.fileSize = stat.size
  cfg.baseName = path.basename(cfg.file)
  const sliceSize = cfg.sliceSize || getSliceSize(cfg.fileSize)
  const isDirect = cfg.fileSize < sliceSize * 2

  log(`文件: ${cfg.baseName} (${cfg.fileSize} bytes), 模式: ${isDirect ? '直传' : '分片'}, 分片大小: ${sliceSize}`)

  log('阶段 apply(ApplyUploadInfo)...')
  const applied = await applyUpload(cfg)
  const ctx = {
    oid: applied.oid,
    signature: applied.signature,
    tosDomain: applied.tosDomain,
    sessionKey: applied.sessionKey,
    uploadHeader: resolveHeader(applied.serverUploadHeader, { gatewayUpload: !isDirect }),
  }
  log(`apply 成功 oid=${ctx.oid}`)

  const fd = fs.openSync(cfg.file, 'r')
  const uploadStart = Date.now()
  try {
    if (isDirect) {
      const buffer = readSlice(fd, 0, cfg.fileSize)
      const crc32 = computeCrc32(buffer)
      log('阶段 upload(直传整包)...')
      await uploadChunk(cfg, ctx, { url: `${ctx.tosDomain}/${ctx.oid}`, buffer, crc32 })
    } else {
      log('阶段 init...')
      ctx.uploadId = await initUpload(cfg, ctx)
      log(`init 成功 uploadId=${ctx.uploadId}`)

      const slices = buildSlices(cfg.fileSize, sliceSize)
      const crc32List = new Array(slices.length)
      const parallel = Math.max(1, Math.min(cfg.uploadSliceCount, slices.length))
      log(`阶段 upload: 共 ${slices.length} 片, 并发 ${parallel}...`)

      let next = 0
      let done = 0
      const worker = async () => {
        while (next < slices.length) {
          const idx = next++
          const { start, end } = slices[idx]
          const buffer = readSlice(fd, start, end)
          const crc32 = computeCrc32(buffer)
          crc32List[idx] = crc32
          const url = `${ctx.tosDomain}/${ctx.oid}?partNumber=${idx + 1}&uploadID=${ctx.uploadId}`
          await uploadChunk(cfg, ctx, { url, buffer, crc32 })
          done++
          log(`分片 ${idx + 1}/${slices.length} 完成 (${Math.round((done / slices.length) * 100)}%)`)
        }
      }
      await Promise.all(Array.from({ length: parallel }, () => worker()))

      log('阶段 merge...')
      await mergeUpload(cfg, ctx, crc32List)
      log('merge 成功')
    }
  } finally {
    fs.closeSync(fd)
  }
  const uploadDurationMs = Date.now() - uploadStart

  log('阶段 commit(CommitUploadInfo)...')
  const data = await commitUpload(cfg, ctx, uploadDurationMs)
  log('commit 成功')
  return data
}

// ------------------------------ CLI ------------------------------
const REMOVED_OPTIONS = [
  'access-key-id',
  'secret-access-key',
  'session-token',
  'sts-token',
  'current-time',
  'expired-time',
  'space-name',
  'image-service-id',
  'imagex-host',
  'region',
  'protocol',
  'account-id',
  'host',
  'kind',
  'use-server-current-time',
  'no-server-current-time',
  'file-type',
  'file-extension',
  'use-file-extension',
  'vod-credential',
  'imagex-credential',
  'mcp-endpoint',
  'mcp-token',
  'no-set-public',
]

function parseArgs(argv) {
  const args = {}
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith('--')) {
      const key = a.slice(2)
      const next = argv[i + 1]
      if (next === undefined || next.startsWith('--')) {
        args[key] = true
      } else {
        args[key] = next
        i++
      }
    }
  }
  return args
}

async function readUploadSessionFromStdin() {
  const input = process.stdin
  if (!input.isTTY || typeof input.setRawMode !== 'function') {
    const chunks = []
    for await (const chunk of input) chunks.push(Buffer.from(chunk))
    return Buffer.concat(chunks).toString('utf8').trim()
  }

  return new Promise((resolve, reject) => {
    const chunks = []
    let rawModeEnabled = false
    let settled = false

    const cleanup = () => {
      input.off('data', onData)
      input.off('end', onEnd)
      input.off('error', onError)
      if (rawModeEnabled) input.setRawMode(false)
      input.pause()
    }
    const finish = (error) => {
      if (settled) return
      settled = true
      cleanup()
      if (error) reject(error)
      else resolve(Buffer.concat(chunks).toString('utf8').trim())
    }
    const onData = (chunk) => {
      const data = Buffer.from(chunk)
      for (let i = 0; i < data.length; i++) {
        if (data[i] === 3) {
          finish(new Error('从 stdin 读取 upload session 已取消'))
          return
        }
        if (data[i] === 10 || data[i] === 13) {
          if (i > 0) chunks.push(data.subarray(0, i))
          finish()
          return
        }
      }
      chunks.push(data)
    }
    const onEnd = () => finish()
    const onError = (error) => finish(error)

    input.on('data', onData)
    input.on('end', onEnd)
    input.on('error', onError)
    try {
      input.setRawMode(true)
      rawModeEnabled = true
      input.resume()
    } catch (error) {
      finish(error)
    }
  })
}

function cleanCredField(v) {
  let s = String(v).trim()
  while (s.length >= 2 && ['`', "'", '"'].includes(s[0]) && s[s.length - 1] === s[0]) {
    s = s.slice(1, -1).trim()
  }
  return s
}

function buildConfig(args, expectedKind, issuedCredential) {
  let credentials = {}
  let vodCred = expectedKind === 'video' && issuedCredential ? { ...issuedCredential } : null
  let imagexCred = expectedKind === 'image' && issuedCredential ? { ...issuedCredential } : null
  if (vodCred) {
    for (const k of [
      'access_key_id', 'secret_access_key', 'session_token',
      'current_time', 'expired_time', 'region', 'upload_host', 'space_name',
    ]) {
      if (typeof vodCred[k] === 'string') vodCred[k] = cleanCredField(vodCred[k])
    }
    credentials = {
      accessKeyId: vodCred.access_key_id,
      secretAccessKey: vodCred.secret_access_key,
      sessionToken: vodCred.session_token,
      currentTime: vodCred.current_time || undefined,
      expiredTime: vodCred.expired_time || undefined,
    }
  }
  if (imagexCred) {
    for (const k of [
      'access_key_id', 'secret_access_key', 'session_token',
      'current_time', 'expired_time', 'region', 'upload_host', 'image_service_id',
    ]) {
      if (typeof imagexCred[k] === 'string') imagexCred[k] = cleanCredField(imagexCred[k])
    }
    credentials = {
      accessKeyId: imagexCred.access_key_id,
      secretAccessKey: imagexCred.secret_access_key,
      sessionToken: imagexCred.session_token,
      currentTime: imagexCred.current_time || undefined,
      expiredTime: imagexCred.expired_time || undefined,
    }
  }

  const credHost = vodCred?.upload_host
    ? (/^https?:\/\//.test(vodCred.upload_host) ? vodCred.upload_host : `https://${vodCred.upload_host}`)
    : undefined
  const credImagexHost = imagexCred?.upload_host
    ? (/^https?:\/\//.test(imagexCred.upload_host) ? imagexCred.upload_host : `https://${imagexCred.upload_host}`)
    : undefined
  const kind = expectedKind

  const cfg = {
    file: args.file,
    kind,
    credentialCount: Number(!!vodCred) + Number(!!imagexCred),
    unsupportedOptions: REMOVED_OPTIONS.filter((key) => args[key] !== undefined),
    spaceName: vodCred?.space_name,
    region: vodCred?.region || imagexCred?.region || DEFAULT_REGION,
    fileType: 'video',
    fileName: args['file-name'] || undefined,
    fileExtension: undefined,
    useFileExtension: false,
    storageClass: args['storage-class'] !== undefined ? Number(args['storage-class']) : undefined,
    videoHost: credHost || undefined,
    schema: args['schema'] || 'https',
    accountId: (vodCred?.top_account_id != null ? String(vodCred.top_account_id) : undefined)
      || (imagexCred?.top_account_id != null ? String(imagexCred.top_account_id) : undefined),
    useServerCurrentTime: true,
    sliceSize: args['slice-size'] ? Number(args['slice-size']) : undefined,
    uploadSliceCount: args['parallel'] ? Number(args['parallel']) : 5,
    retryUploadTime: args['retry-upload'] ? Number(args['retry-upload']) : 2,
    retryTaskTime: args['retry-task'] ? Number(args['retry-task']) : 2,
    retryInterval: 2000,
    requestTimeout: 5 * 60 * 1000,
    uploadTimeout: 30 * 60 * 1000,
    processAction: args['process-action'] ? JSON.parse(args['process-action']) : undefined,
    callbackArgs: args['callback-args'] || undefined,
    expireTime: args['expire-time'] || undefined,
    imageServiceId: imagexCred?.image_service_id || undefined,
    imagexHost: credImagexHost,
    storeKey: args['store-key'] || undefined,
    skipMeta: args['skip-meta'] !== undefined ? true : false,
    credentials,
  }

  const host = cfg.videoHost || ''
  const looksInner = /tiktok\.com/i.test(host) || /(^|[^a-z])sg([^a-z]|$)/i.test(cfg.region) || vodCred?.provider === 1
  cfg.protocol = looksInner ? 'inner' : 'volc'

  const ihost = cfg.imagexHost || ''
  const looksImagexInner = /tiktok\.com/i.test(ihost) || /(^|[^a-z])sg([^a-z]|$)/i.test(cfg.region)
  cfg.imagexProtocol = looksImagexInner ? 'inner' : 'volc'
  return cfg
}

function validate(cfg) {
  const errors = []
  if (cfg.credentialCount !== 1)
    errors.push(cfg.kind === 'image'
      ? 'upload session 缺少 imagex_credential'
      : 'upload session 缺少 vod_credential')
  if (cfg.unsupportedOptions.length > 0)
    errors.push(`不再支持的参数: ${cfg.unsupportedOptions.map((key) => `--${key}`).join(', ')}`)
  if (!cfg.file) errors.push('缺少 --file <文件路径>')
  else if (!fs.existsSync(cfg.file)) errors.push(`文件不存在: ${cfg.file}`)
  else {
    const extension = path.extname(cfg.file).slice(1).toLowerCase()
    const supported = cfg.kind === 'image' ? IMAGE_EXTENSIONS : VIDEO_EXTENSIONS
    if (!supported.has(extension)) {
      errors.push(cfg.kind === 'image'
        ? `仅支持图片上传，当前文件扩展名不受支持: ${extension || '(无扩展名)'}`
        : `仅支持视频上传，音频或其他文件类型暂不支持: ${extension || '(无扩展名)'}`)
    }
  }
  if (cfg.credentialCount === 1) {
    if (!cfg.credentials.accessKeyId) errors.push('MCP 短期凭证缺少 access_key_id')
    if (!cfg.credentials.secretAccessKey)
      errors.push('MCP 短期凭证缺少 secret_access_key')
    if (cfg.kind === 'image') {
      if (!cfg.imageServiceId)
        errors.push('MCP imagex_credential 缺少 image_service_id')
      if (cfg.imagexProtocol === 'inner' && !cfg.imagexHost)
        errors.push('MCP imagex_credential 缺少 SG/inner ImageX 所需的 upload_host')
    } else {
      if (!cfg.spaceName) errors.push('MCP vod_credential 缺少 space_name')
      if (cfg.protocol === 'inner' && !cfg.videoHost)
        errors.push('MCP vod_credential 缺少 inner 协议所需的 upload_host')
    }
  }
  if (cfg.kind === 'video') {
    if (!cfg.finalizeToken) errors.push('upload session 缺少 video_finalize.token')
    if (!isTrustedFinalizeURL(cfg.finalizeURL)) errors.push('upload session 缺少可信的 video_finalize.url')
  }
  return errors
}

function isTrustedFinalizeURL(value) {
  try {
    const parsed = new URL(value)
    const trustedHost = parsed.hostname === 'capcut.com' || parsed.hostname.endsWith('.capcut.com')
    return parsed.protocol === 'https:' && trustedHost && parsed.pathname === '/api/external_mcp/upload/finalize'
  } catch {
    return false
  }
}

function parseUploadFiles(args) {
  const hasFile = args.file !== undefined
  const hasFiles = args.files !== undefined
  if (hasFile === hasFiles) {
    throw new Error('必须且只能提供 --file <path> 或 --files \'<JSON数组>\'')
  }
  if (hasFile) {
    return [{ file: String(args.file), clientId: args['client-id'] ? String(args['client-id']).trim() : '' }]
  }

  const files = JSON.parse(args.files)
  if (!Array.isArray(files) || files.length === 0 || files.length > 16) {
    throw new Error('--files 必须是包含 1 到 16 个文件路径的 JSON 数组')
  }
  if (files.some((item) => !item || typeof item !== 'object' || Array.isArray(item) ||
    typeof item.file !== 'string' || !item.file.trim() ||
    typeof item.client_id !== 'string' || !item.client_id.trim())) {
    throw new Error('--files 中的每一项都必须包含非空 file 和 client_id')
  }
  const clientIds = files.map((item) => item.client_id.trim())
  if (new Set(clientIds).size !== clientIds.length) {
    throw new Error('--files 中的 client_id 必须唯一')
  }
  return files.map((item) => ({ file: item.file.trim(), clientId: item.client_id.trim() }))
}

function classifyUploadKind(file) {
  const extension = path.extname(file).slice(1).toLowerCase()
  if (VIDEO_EXTENSIONS.has(extension)) return 'video'
  if (IMAGE_EXTENSIONS.has(extension)) return 'image'
  throw new Error(`仅支持视频和图片，音频或其他文件类型暂不支持: ${file}`)
}

function buildUploadConfigs(args, files, session) {
  if (!session || session.status !== 'success') {
    throw new Error('--upload-session 必须是 capcut_asset_upload_credential 的完整成功响应')
  }
  return files.map((item) => {
    const kind = classifyUploadKind(item.file)
    const itemArgs = { ...args, file: item.file }
    delete itemArgs.files
    const credential = kind === 'video' ? session.vod_credential : session.imagex_credential
    const cfg = buildConfig(itemArgs, kind, credential)
    cfg.clientId = item.clientId
    cfg.finalizeURL = session.video_finalize?.url || ''
    cfg.finalizeToken = session.video_finalize?.token || ''
    return cfg
  })
}

function buildFinalizeOnlyConfig(args, session) {
  if (!session || session.status !== 'success') {
    throw new Error('--upload-session 必须是 capcut_asset_upload_credential 的完整成功响应')
  }
  const vid = typeof args['finalize-vid'] === 'string' ? args['finalize-vid'].trim() : ''
  if (!vid) throw new Error('--finalize-vid 不能为空')

  const clientId = typeof args['client-id'] === 'string' ? args['client-id'].trim() : ''

  const cfg = {
    clientId,
    finalizeURL: session.video_finalize?.url || '',
    finalizeToken: session.video_finalize?.token || '',
    retryTaskTime: args['retry-task'] ? Number(args['retry-task']) : 2,
    retryInterval: 2000,
    requestTimeout: 5 * 60 * 1000,
  }
  if (!cfg.finalizeToken) throw new Error('upload session 缺少 video_finalize.token')
  if (!isTrustedFinalizeURL(cfg.finalizeURL)) throw new Error('upload session 缺少可信的 video_finalize.url')
  return { cfg, vid }
}

async function runFinalizeOnly(args, session) {
  const { cfg, vid } = buildFinalizeOnlyConfig(args, session)
  try {
    const finalize = await finalizeVideo(cfg, vid)
    return {
      success: true,
      uploadSuccess: true,
      stage: 'set_public',
      clientId: cfg.clientId,
      kind: 'video',
      vid,
      setPublic: { success: true, result: finalize },
    }
  } catch (err) {
    return {
      success: false,
      uploadSuccess: true,
      stage: 'set_public',
      retryable: true,
      clientId: cfg.clientId,
      kind: 'video',
      vid,
      setPublic: { success: false, error: err.message },
      error: err.message,
    }
  }
}

async function uploadOne(cfg) {
  if (cfg.kind === 'image') {
    log(`目标: ImageX（图片上传）协议: ${cfg.imagexProtocol}${cfg.imagexProtocol === 'inner' ? '（CapCut AI Search / tiktok ImageX 网关，AWS4）' : '（火山公有云 OpenAPI）'}`)
    const data = await uploadImage(cfg)
    const uri = data?.Uri || null
    log(`上传成功! Uri=${uri}`)
    return { success: true, file: cfg.file, clientId: cfg.clientId, kind: 'image', uri, result: data }
  }

  log(`协议: ${cfg.protocol}${cfg.protocol === 'inner' ? '（CapCut AI Search / tiktok VOD 网关）' : '（火山公有云 OpenAPI）'}`)
  const data = cfg.protocol === 'inner' ? await uploadInner(cfg) : await upload(cfg)
  const vid = data?.Vid || data?.vid || null

  if (!vid) {
    return {
      success: false,
      uploadSuccess: true,
      stage: 'set_public',
      file: cfg.file,
      clientId: cfg.clientId,
      kind: 'video',
      vid: null,
      error: 'VOD 上传成功但未返回 vid',
    }
  }
  try {
    log(`完成视频上传: 校验 finalize capability 并设公开 vid=${vid}`)
    const finalize = await finalizeVideo(cfg, vid)
    log('视频 finalize 成功')
    return {
      success: true,
      file: cfg.file,
      clientId: cfg.clientId,
      kind: 'video',
      vid,
      setPublic: { success: true, result: finalize },
      result: data,
    }
  } catch (err) {
    log(`视频 finalize 失败（上传已成功，不重传）: ${err.message}`)
    return {
      success: false,
      uploadSuccess: true,
      stage: 'set_public',
      retryable: true,
      file: cfg.file,
      clientId: cfg.clientId,
      kind: 'video',
      vid,
      setPublic: { success: false, error: err.message },
      error: err.message,
    }
  }
}

const HELP = `capcut-upload.mjs — CapCut 媒资上传（视频->VOD，图片->ImageX；Node，无第三方依赖；暂不支持音频）

必填：
  文件（必须且只能选择一种；批量最多 16 个）：
    --file <path>            单个待上传文件路径
    --files '<JSON数组>'     {client_id,file} 对象数组，支持视频/图片混合批次
  凭证（必须且只能选择一种）：
    --upload-session '<JSON>'  直接传入 capcut_asset_upload_credential 的完整成功响应
    --upload-session-stdin     从 stdin 安全读取完整成功响应；TTY 输入以换行结束
                               自动化环境优先使用此方式，避免凭证出现在进程参数中

可选（通用）：
  --client-id <id>          单文件模式对应 credential 请求的 client_id，用于结果标识
  --file-name <name>         指定媒资文件名
  --slice-size <bytes>       自定义分片大小
  --parallel <n>             分片并发数，默认 5
  --process-action '<JSON>'  VOD 转码 / ImageX 处理 Functions 数组
  --json                     以 JSON 输出结果到 stdout
  --help                     显示帮助

视频 finalize 重试（不重传文件）：
  --finalize-vid <vid>       与一种 upload-session 输入及 --client-id 一起使用，仅重试设公开

可选（视频 -> VOD）：
  --storage-class <n>        存储类型
  --callback-args <str>      回调参数
  --expire-time <ISO>        媒资过期时间
  上传完成后脚本强制调用 upload session 中的 capability finalize endpoint，服务端验证
  服务端验证短时 capability 后设公开。任一步失败均返回整体失败。

可选（图片 -> ImageX）：
  --store-key <key>          指定存储 StoreKey（透传为 StoreKeys）
  --skip-meta                CommitImageUpload 时带 SkipMeta=true（跳过元信息解析）

示例：
  # 单个视频：启动后从 stdin 输入完整响应并换行
  node scripts/capcut-upload.mjs --file ./demo.mp4 \\
    --client-id video-1 \\
    --upload-session-stdin \\
    --json

  # 单个图片
  node scripts/capcut-upload.mjs --file ./demo.png \\
    --client-id image-1 \\
    --upload-session-stdin \\
    --json

  # 视频和图片混合批次
  node scripts/capcut-upload.mjs \\
    --files '[{"client_id":"video-1","file":"./demo.mp4"},{"client_id":"image-1","file":"./cover.png"}]' \\
    --upload-session-stdin \\
    --json

  # 视频已上传但 finalize 失败：仅重试设公开
  node scripts/capcut-upload.mjs --finalize-vid '<VID>' \\
    --client-id video-1 \\
    --upload-session-stdin \\
    --json
`

async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.help || Object.keys(args).length === 0) {
    process.stdout.write(HELP)
    process.exit(0)
  }
  let files
  let configs
  let session
  try {
    const hasInlineSession = args['upload-session'] !== undefined
    const hasStdinSession = args['upload-session-stdin'] !== undefined
    if (hasInlineSession && hasStdinSession) {
      throw new Error('--upload-session 与 --upload-session-stdin 不能同时使用')
    }
    if (!hasInlineSession && !hasStdinSession) {
      throw new Error('缺少 --upload-session <JSON> 或 --upload-session-stdin')
    }
    const sessionJson = hasStdinSession ? await readUploadSessionFromStdin() : args['upload-session']
    if (!sessionJson) throw new Error('stdin 中缺少完整 upload session JSON')
    session = JSON.parse(sessionJson)
    if (args['finalize-vid'] !== undefined) {
      if (args.file !== undefined || args.files !== undefined) {
        throw new Error('--finalize-vid 不能与 --file 或 --files 同时使用')
      }
      const output = await runFinalizeOnly(args, session)
      if (args.json) process.stdout.write(JSON.stringify(output) + '\n')
      else log(JSON.stringify(output, null, 2))
      process.exit(output.success ? 0 : 1)
    }
    files = parseUploadFiles(args)
    configs = buildUploadConfigs(args, files, session)
  } catch (err) {
    const errors = [`参数解析失败: ${err.message}`]
    if (args.json) {
      process.stdout.write(JSON.stringify({ success: false, errors }) + '\n')
    } else {
      log('参数错误:\n  - ' + errors.join('\n  - '))
    }
    process.exit(2)
  }

  const errors = configs.flatMap((cfg) => validate(cfg).map((error) => `${cfg.file}: ${error}`))
  if (errors.length > 0) {
    if (args.json) {
      process.stdout.write(JSON.stringify({ success: false, errors }) + '\n')
    } else {
      log('参数错误:\n  - ' + errors.join('\n  - '))
    }
    process.exit(2)
  }

  const results = []
  for (const cfg of configs) {
    try {
      results.push(await uploadOne(cfg))
    } catch (err) {
      log(`上传失败: ${cfg.file}: ${err.message}`)
      results.push({ success: false, file: cfg.file, kind: cfg.kind, error: err.message })
    }
  }

  const success = results.every((result) => result.success)
  const output = args.files === undefined ? results[0] : { success, results }
  if (args.json) process.stdout.write(JSON.stringify(output) + '\n')
  else log(JSON.stringify(output, null, 2))
  process.exit(success ? 0 : 1)
}

main()
