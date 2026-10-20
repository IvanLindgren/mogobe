/* Original mini-game SWFs stay local; authenticated runs/results live on FastAPI. */
let minigameOpening = false;
let minigameCurrent = null;
let minigameFinishing = false;
window.mogobeMinigame = {state:'closed'};

async function minigameRequest(path, body) {
  const response = await fetch('/api/minigames'+path, {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body??{})
  });
  const data = await response.json();
  if(!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Миниигра недоступна.');
  return data;
}

window.openMogobeMinigame = async key => {
  if(minigameOpening || minigameCurrent || window.mogobeScene?.state!=='world' || leavingWorld) return;
  minigameOpening = true;
  let run;
  try {
    run = await minigameRequest('/'+encodeURIComponent(key)+'/start');
    if(leavingWorld || window.mogobeScene?.state!=='world') {
      await minigameRequest('/runs/'+run.id+'/finish',{score:0,completed:false,cancelled:true});
      return;
    }
    minigameCurrent = run;
    minigameFinishing = false;
    window.mogobeMinigame = {state:'loading',key:run.key,id:run.id};
    if(!window.player?.ruffle().callExternalInterface('openMinigame',run)) {
      await minigameRequest('/runs/'+run.id+'/finish',{score:0,completed:false,cancelled:true});
      minigameCurrent = null;
      window.mogobeMinigame = {state:'closed'};
      throw Error('Закрой открытое окно и попробуй запустить рыбалку ещё раз.');
    }
  } catch(error) {
    if(!leavingWorld) showMogobePopup(error.message);
  } finally { minigameOpening=false; }
};

window.onMogobeMinigameReady = id => {
  if(minigameCurrent?.id===id) window.mogobeMinigame = {state:'playing',key:minigameCurrent.key,id};
};
window.onMogobeMinigameFinished = (id,score,completed,message) => {
  // Leave the original AS3 event dispatch before disposing its movie.
  setTimeout(()=>finishMogobeMinigame(id,score,completed,message),0);
};

async function finishMogobeMinigame(id, score, completed, message='') {
  if(minigameCurrent?.id!==id || minigameFinishing) return;
  minigameFinishing = true;
  window.mogobeMinigame = {...window.mogobeMinigame,state:'finishing'};
  let showingResult = false;
  try {
    let result;
    // A repeated request is idempotent, including a lost successful response.
    for(let attempt=0;attempt<2;attempt++) {
      try { result=await minigameRequest('/runs/'+id+'/finish',{score,completed,cancelled:Boolean(message)});break; }
      catch(error) { if(attempt===1) throw error; }
    }
    if(message) {
      window.mogobeMinigame = {state:'closed',result};
      setTimeout(()=>showMogobePopup(message),0);
    } else {
      showingResult = Boolean(window.player?.ruffle().callExternalInterface('showMinigameResult',result));
      if(!showingResult) throw Error('Награда сохранена, но не удалось открыть оригинальный экран результата.');
      window.mogobeMinigame = {state:'result',id,key:minigameCurrent.key,result};
    }
  } catch(error) {
    // Rejecting a result must not strand the player or leave an active payout.
    try { await minigameRequest('/runs/'+id+'/finish',{score:0,completed:false,cancelled:true}); } catch {}
    window.mogobeMinigame = {state:'closed',error:error.message};
    if(!leavingWorld) setTimeout(()=>showMogobePopup(error.message),0);
  } finally {
    if(!showingResult) {
      window.player?.ruffle().callExternalInterface('closeMinigame');
      minigameCurrent = null;
      minigameFinishing = false;
    }
  }
}

window.onMogobeMinigameResultClosed = id => {
  if(minigameCurrent?.id!==id) return;
  minigameCurrent = null;
  minigameFinishing = false;
  window.mogobeMinigame = {...window.mogobeMinigame,state:'closed'};
};
