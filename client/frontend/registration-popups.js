/* The supplied Popups.swf renders messages; HTML only hosts the modal player. */
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'registration-popup';
  dialog.setAttribute('aria-label','Сообщение');
  const movie = document.createElement('div'); movie.id = 'registration-popup-movie';
  const fallback = document.createElement('div'); fallback.hidden = true;
  const fallbackText = document.createElement('p');
  const fallbackClose = document.createElement('button');
  fallbackClose.type = 'button'; fallbackClose.textContent = 'Понятно';
  fallback.append(fallbackText,fallbackClose); dialog.append(movie,fallback);
  document.body.appendChild(dialog);
  let player, ready, restoreFocus, generation = 0;
  window.mogobePopup = {state:'closed',message:'',original:false};
  function close() {
    generation++;
    if(dialog.open) dialog.close();
    window.mogobePopup.state = 'closed';
    if(restoreFocus?.isConnected) restoreFocus.focus();
  }
  window.onMogobePopupClosed = close;
  fallbackClose.addEventListener('click',close);
  dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  function load() {
    if(ready) return ready;
    ready = new Promise((resolve,reject)=>{
      const timeout = setTimeout(()=>reject(new Error('Загрузка окна сообщения не завершилась.')),15000);
      window.onMogobePopupReady = ()=>{clearTimeout(timeout);resolve();};
      window.onMogobePopupFailed = ()=>{clearTimeout(timeout);reject(new Error('Не удалось загрузить окно сообщения.'));};
      try {
        player = RufflePlayer.newest().createPlayer();
        player.tabIndex = 0;
        window.registrationPopupPlayer = player;
        movie.appendChild(player);
        player.ruffle().load({url:'/compat/MogobeHost.swf',base:location.origin+'/',
          wmode:'transparent',parameters:{popupMode:'true'}}).catch(error=>{clearTimeout(timeout);reject(error);});
      } catch(error) { clearTimeout(timeout);reject(error); }
    });
    return ready;
  }
  window.showMogobePopup = async (message, options = {}) => {
    const current = ++generation;
    if(!dialog.open) { restoreFocus=document.activeElement; dialog.showModal(); }
    dialog.setAttribute('aria-label',message);
    window.mogobePopup = {state:'loading',message,original:false};
    try {
      await load();
      if(current !== generation) return;
      player.ruffle().callExternalInterface('showMessage',message,options.kind==='commands');
      window.mogobePopup = {state:'open',message,original:true};
      player.focus();
    } catch {
      if(current !== generation) return;
      movie.hidden = true; fallback.hidden = false;
      fallbackText.textContent = message;
      window.mogobePopup = {state:'open',message,original:false};
      fallbackClose.focus();
    }
  };
})();
