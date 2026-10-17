import { nicknameError } from './pvpEntry.js'
export const accountError = value => /^[A-Za-z0-9_]{4,24}$/.test(value.trim()) ? '' : '账号需为 4–24 位字母、数字或下划线'
export const passwordError = value => value.length >= 8 && value.length <= 64 ? '' : '密码需为 8–64 个字符'
export function registrationErrors(form) {
 return { account: accountError(form.account), display_name: nicknameError(form.display_name), password: passwordError(form.password), confirm: form.confirm === form.password ? '' : '两次输入的密码不一致', registration_code: /^[A-Z2-9]{16}$/i.test(form.registration_code.replace(/-/g, '').trim()) ? '' : '请输入 16 位有效注册码' }
}
