import { mount } from 'svelte'
import { registerSW } from 'virtual:pwa-register'
import './app.css'
import App from './App.svelte'

registerSW({ immediate: true })

const target = /** @type {HTMLElement} */ (document.getElementById('app'))
const app = mount(App, { target })

export default app