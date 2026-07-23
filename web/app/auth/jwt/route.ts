import { resolveServerConsoleApiUrl } from '@/service/server'
import { basePath } from '@/utils/var'

const JWT_LOGIN_PATH = '/portal/jwt-login'
const AUTH_JWT_PATH = `${basePath}/auth/jwt`

const getSetCookieHeaders = (headers: Headers) => {
  const getSetCookie = Reflect.get(headers, 'getSetCookie')

  if (typeof getSetCookie === 'function') {
    const values: unknown = getSetCookie.call(headers)
    return Array.isArray(values)
      ? values.filter((value): value is string => typeof value === 'string')
      : []
  }

  const setCookie = headers.get('set-cookie')
  return setCookie ? [setCookie] : []
}

const createRedirectResponse = (pathname: string, setCookies: string[] = []) => {
  const headers = new Headers({
    'Cache-Control': 'no-store',
    Location: pathname,
  })

  for (const cookie of setCookies) headers.append('Set-Cookie', cookie)

  return new Response(null, {
    status: 303,
    headers,
  })
}

const createSigninRedirectResponse = () =>
  createRedirectResponse(`${basePath}/signin?message=${encodeURIComponent('免登失败，请使用邮箱密码登录')}`)

export async function GET(request: Request) {
  const requestUrl = new URL(request.url)
  const token = requestUrl.searchParams.get('token')

  if (!token) return createSigninRedirectResponse()

  const jwtLoginUrl = resolveServerConsoleApiUrl(JWT_LOGIN_PATH)
  if (!jwtLoginUrl) return createSigninRedirectResponse()

  try {
    const response = await fetch(jwtLoginUrl, {
      method: 'POST',
      headers: new Headers({
        'Content-Type': 'application/json',
        'X-Portal-API-Key': process.env.PORTAL_API_KEY || '',
      }),
      body: JSON.stringify({ token }),
      cache: 'no-store',
    })

    if (!response.ok) return createSigninRedirectResponse()

    // 提取 Set-Cookie headers，302 重定向到控制台首页
    const redirectTarget = requestUrl.searchParams.get('redirect_url') || `${basePath}/`

    return createRedirectResponse(redirectTarget, getSetCookieHeaders(response.headers))
  } catch {
    return createSigninRedirectResponse()
  }
}
