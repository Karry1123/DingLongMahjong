<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '../services/authApi.js'
import { saveAuth } from '../stores/auth.js'
import { accountError, passwordError, registrationErrors } from '../utils/authValidation.js'
import { safeRedirect } from '../router/guards.js'
const props = defineProps({ register: Boolean })
const route = useRoute(), router = useRouter()
const form = reactive({ account:'', display_name:'', password:'', confirm:'', registration_code:'' }), touched = reactive({})
const busy = ref(false), error = ref('')
const errors = computed(() => props.register ? registrationErrors(form) : { account:accountError(form.account), password:passwordError(form.password) })
const fields = computed(() => [ ['account','账号','text','username'], ...(props.register ? [['display_name','昵称','text','nickname']] : []), ['password','密码','password',props.register ? 'new-password' : 'current-password'], ...(props.register ? [['confirm','确认密码','password','new-password'],['registration_code','注册码','text','off']] : []) ])
async function submit() {
 fields.value.forEach(([key]) => { touched[key] = true })
 if (Object.values(errors.value).some(Boolean) || busy.value) return
 busy.value = true; error.value = ''
 try { const { confirm, ...body } = form; body.account = body.account.trim(); body.display_name = body.display_name.trim(); body.registration_code = body.registration_code.trim(); await saveAuth(await (props.register ? register(body) : login({ account:form.account.trim(), password:form.password }))); await router.replace(safeRedirect(route.query.redirect)) }
 catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>
<template><section class="auth-intro"><p class="eyebrow">一桌风雅 · 四方相逢</p><h1>{{ props.register ? '注册账号' : '欢迎入席' }}</h1><p>{{ props.register ? '凭注册码，与好友相约一桌。' : '登录账号，赴一场好友牌约。' }}</p></section><form class="card stack auth-form" novalidate @submit.prevent="submit"><label v-for="[key,label,type,autocomplete] in fields" :key="key" :for="key">{{ label }}<input :id="key" v-model="form[key]" :type="type" :autocomplete="autocomplete" autocapitalize="none" :spellcheck="false" :maxlength="key === 'account' ? 24 : key === 'registration_code' ? 19 : key === 'display_name' ? 12 : 64" :aria-invalid="!!(touched[key] && errors[key])" :aria-describedby="`${key}-error`" @blur="touched[key] = true" /><small v-if="touched[key] && errors[key]" :id="`${key}-error`" class="error">{{ errors[key] }}</small></label><p v-if="error || route.query.error" class="error" role="alert">{{ error || route.query.error }}</p><button class="primary" :disabled="busy">{{ busy ? '请稍候…' : props.register ? '注册并登录' : '登录' }}</button><RouterLink :to="{ path:props.register ? '/login' : '/register', query: { redirect:route.query.redirect } }">{{ props.register ? '已有账号？去登录' : '持有注册码？注册账号' }}</RouterLink></form></template>
