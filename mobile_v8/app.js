const screens=new Map([...document.querySelectorAll('[data-panel]')].map(el=>[el.dataset.panel,el]));
const navButtons=[...document.querySelectorAll('[data-nav]')];
function navigate(tab){if(!screens.has(tab))return;
for(const [name,screen] of screens)screen.hidden=name!==tab;
for(const button of navButtons){const active=button.dataset.nav===tab;button.classList.toggle('active',active);button.setAttribute('aria-current',active?'page':'false');}
if(location.hash!=='#'+tab)history.replaceState(null,'','#'+tab);}
for(const button of navButtons)button.addEventListener('click',()=>navigate(button.dataset.nav));
navigate(screens.has(location.hash.slice(1))?location.hash.slice(1):'home');
addEventListener('hashchange',()=>navigate(screens.has(location.hash.slice(1))?location.hash.slice(1):'home'));
let pending=null;const install=document.querySelector('#install');
addEventListener('beforeinstallprompt',e=>{e.preventDefault();pending=e;install.disabled=false;install.textContent='Install safe paper preview';});
install.addEventListener('click',async()=>{if(!pending)return;pending.prompt();await pending.userChoice;pending=null;install.disabled=true;install.textContent='Use Chrome menu to install';});
if('serviceWorker' in navigator)addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{}));
