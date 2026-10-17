package {
    import flash.display.BitmapData;
    import flash.utils.ByteArray;
    import flash.display.DisplayObject;
    import flash.display.DisplayObjectContainer;
    import flash.display.Loader;
    import flash.display.MovieClip;
    import flash.display.Shape;
    import flash.display.Sprite;
    import flash.utils.getTimer;
    import flash.events.Event;
    import flash.events.MouseEvent;
    import flash.events.IOErrorEvent;
    import flash.events.SecurityErrorEvent;
    import flash.events.KeyboardEvent;
    import flash.external.ExternalInterface;
    import flash.net.URLRequest;
    import flash.geom.Rectangle;
    import flash.geom.Matrix;
    import flash.text.TextField;
    import flash.text.TextFormat;
    import flash.text.TextFormatAlign;
    import flash.system.ApplicationDomain;
    import flash.system.LoaderContext;
    import flash.utils.getQualifiedClassName;

    public dynamic class MogobeHost extends MovieClip {
        private var gameLoader:Loader;
        private var originalPreloader:Loader;
        private var scoreSignsShown:int = 0;
        private var lastScoreSign:String = "";
        private var profileIconLoader:Loader;
        private var profileIconDomain:ApplicationDomain;
        private var mapAssetsLoader:Loader;
        private var mapAssetsDomain:ApplicationDomain;
        private var mapAssetsError:String = "";
        private var mapAssetsLoads:int = 0;
        private var lastState:String = "";
        private var hasLobby:Boolean;
        private var mainClip:DisplayObjectContainer;
        private var cookieManager:Object;
        private var currentLogin:DisplayObjectContainer;
        private var hookedLogin:DisplayObjectContainer;
        private var laidOutLogin:DisplayObjectContainer;
        private var loginKind:String = "";
        private var lastLoginView:String = "";
        private var rememberedNames:String = "";
        private var registrationUser:String = "";
        private var registrationPending:Boolean = false;
        private var displayNames:Object = {};
        private var popupLoader:Loader;
        private var popupWindow:MovieClip;
        private var popupText:TextField;
        private var popupFont:Object;
        private var worldLoginInfo:Object;
        private var worldStarting:Boolean = false;
        private var hookedServers:DisplayObjectContainer;
        private var serversPresence:Array = [];
        private var worldAvatar:DisplayObject;
        private var socialState:Object = {};
        private var socialPopupStack:Array = [];
        private var pendingMutes:Object = {};
        private var muteSequence:int = 0;
        private var friendHover:MovieClip;
        private var friendHoverText:String = "";
        private var friendHoverTime:int;
        private var friendTooltip:Sprite;

        public function MogobeHost() {
            super();
            if (loaderInfo.parameters.popupMode == "true") {
                loadRegistrationPopup();
                return;
            }
            gameLoader = new Loader();
            gameLoader.addEventListener(Event.ADDED, originalDisplayAdded, true, 200);
            gameLoader.addEventListener(KeyboardEvent.KEY_DOWN, worldChatKey, true, 100);
            gameLoader.addEventListener(MouseEvent.CLICK, worldChatClick, true, 100);
            gameLoader.addEventListener(MouseEvent.CLICK, socialClick, true, 200);
            gameLoader.addEventListener(MouseEvent.CLICK, avatarCameraClick, true, 300);
            gameLoader.addEventListener(MouseEvent.MOUSE_OVER, friendMouseOver, true, 200);
            gameLoader.addEventListener(MouseEvent.MOUSE_OUT, friendMouseOut, true, 200);
            addChild(gameLoader);
            originalPreloader = new Loader();
            originalPreloader.mouseEnabled = false;
            originalPreloader.mouseChildren = false;
            addChild(originalPreloader);
            addEventListener(Event.ENTER_FRAME, inspectScene);
            // Timeline frames and the original controllers can recreate text
            // after ENTER_FRAME. Repair the completed frame before it is drawn.
            addEventListener(Event.EXIT_FRAME, finishOriginalFrame);
            ExternalInterface.addCallback("showOriginalLoading", showOriginalLoading);
            ExternalInterface.addCallback("refreshRememberedState", refreshRememberedState);
            ExternalInterface.addCallback("getLoginControlBounds", getLoginControlBounds);
            ExternalInterface.addCallback("finishRegistrationLogin", finishRegistrationLogin);
            ExternalInterface.addCallback("beginWorld", beginWorld);
            ExternalInterface.addCallback("getWorldAvatar", getWorldAvatar);
            ExternalInterface.addCallback("getWorldAvatars", getWorldAvatars);
            ExternalInterface.addCallback("setServerPresence", setServerPresence);
            ExternalInterface.addCallback("getServerInfo", getServerInfo);
            ExternalInterface.addCallback("getProfileInfo", getProfileInfo);
            ExternalInterface.addCallback("setProfileProgress", setProfileProgress);
            ExternalInterface.addCallback("getExperienceInfo", getExperienceInfo);
            ExternalInterface.addCallback("openOriginalShop",openOriginalShop);
            ExternalInterface.addCallback("refreshOriginalShop",refreshOriginalShop);
            ExternalInterface.addCallback("finishShopPurchase",finishShopPurchase);
            ExternalInterface.addCallback("closeOriginalShop",closeOriginalShop);
            ExternalInterface.addCallback("getShopInfo",getShopInfo);
            ExternalInterface.addCallback("getWorldPanelInfo", getWorldPanelInfo);
            ExternalInterface.addCallback("getWorldMapInfo", getWorldMapInfo);
            ExternalInterface.addCallback("getChatMenuItems", getChatMenuItems);
            ExternalInterface.addCallback("setSocialState", setSocialState);
            ExternalInterface.addCallback("finishMuteChange", finishMuteChange);
            ExternalInterface.addCallback("getFriendsTooltipInfo", getFriendsTooltipInfo);
            ExternalInterface.addCallback("chooseOriginalServer", chooseOriginalServer);
            ExternalInterface.addCallback("getSocialPopupInfo", getSocialPopupInfo);
            ExternalInterface.addCallback("getSocialRowControlBounds", getSocialRowControlBounds);
            ExternalInterface.addCallback("getWorldEffects", getWorldEffects);
            ExternalInterface.addCallback("getWorldCursor", getWorldCursor);
            ExternalInterface.addCallback("getProfileControlBounds", getProfileControlBounds);
            originalPreloader.contentLoaderInfo.addEventListener(Event.COMPLETE, loadOriginalLogin);
            originalPreloader.load(new URLRequest("/compat/OriginalPreloader.swf"));
            preloadWorldMap();
            preloadProfileIcons();
        }

        private function loadRegistrationPopup():void {
            ExternalInterface.addCallback("showMessage", showMessage);
            ExternalInterface.addCallback("getPopupControlBounds", getPopupControlBounds);
            gameLoader = new Loader();
            gameLoader.contentLoaderInfo.addEventListener(Event.COMPLETE, popupFontsLoaded);
            gameLoader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, popupLoadFailed);
            gameLoader.contentLoaderInfo.addEventListener(SecurityErrorEvent.SECURITY_ERROR, popupLoadFailed);
            // The unstarted original login supplies its embedded Russian Arial.
            gameLoader.load(new URLRequest("/Swf/Login.swf"), new LoaderContext(false, ApplicationDomain.currentDomain));
        }

        private function popupLoadFailed(event:Event):void {
            ExternalInterface.call("onMogobePopupFailed");
        }

        private function popupFontsLoaded(event:Event):void {
            gameLoader.contentLoaderInfo.removeEventListener(Event.COMPLETE, popupFontsLoaded);
            var fonts:Class = ApplicationDomain.currentDomain.getDefinition("FontClass") as Class;
            popupFont = Object(fonts).getInstance();
            popupLoader = new Loader();
            popupLoader.contentLoaderInfo.addEventListener(Event.COMPLETE, popupGraphicsLoaded);
            popupLoader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, popupLoadFailed);
            popupLoader.contentLoaderInfo.addEventListener(SecurityErrorEvent.SECURITY_ERROR, popupLoadFailed);
            popupLoader.load(new URLRequest("/Swf/Assets/Popups/RegistrationPopups.swf"), new LoaderContext(false, ApplicationDomain.currentDomain));
        }

        private function popupGraphicsLoaded(event:Event):void {
            var alertClass:Class = ApplicationDomain.currentDomain.getDefinition("mlAlert") as Class;
            popupWindow = new alertClass() as MovieClip;
            popupWindow.stop();
            addChild(popupWindow);
            var bounds:Rectangle = popupWindow.getBounds(popupWindow);
            popupWindow.x = 384 - bounds.x - bounds.width / 2;
            popupWindow.y = 240 - bounds.y - bounds.height / 2;
            popupText = popupFont.addText(Object(popupWindow).txtMessage, "", 420) as TextField;
            Object(popupWindow).txtMessage = popupText;
            var button:MovieClip = Object(popupWindow).btnConfirm as MovieClip;
            button.gotoAndStop("OUT");
            button.buttonMode = true;
            button.mouseChildren = false;
            button.addEventListener(MouseEvent.MOUSE_OVER, popupButtonOver);
            button.addEventListener(MouseEvent.MOUSE_OUT, popupButtonOut);
            button.addEventListener(MouseEvent.CLICK, closePopup);
            stage.addEventListener(KeyboardEvent.KEY_DOWN, popupKeyDown);
            ExternalInterface.call("onMogobePopupReady");
        }

        private function popupButtonOver(event:MouseEvent):void {
            MovieClip(event.currentTarget).gotoAndStop("OVER");
        }

        private function popupButtonOut(event:MouseEvent):void {
            MovieClip(event.currentTarget).gotoAndStop("OUT");
        }

        private function popupKeyDown(event:KeyboardEvent):void {
            if (event.keyCode == 13 || event.keyCode == 27) closePopup(event);
        }

        private function closePopup(event:Event):void {
            ExternalInterface.call("onMogobePopupClosed");
        }

        public function showMessage(message:String):void {
            if (popupText == null) return;
            popupText.text = message;
            popupWindow.focusRect = false;
            stage.focus = popupWindow;
        }

        public function getPopupControlBounds(name:String):Object {
            var control:DisplayObject = findNamed(popupWindow, name, 0);
            if (control == null) return null;
            var bounds:Rectangle = control.getBounds(this);
            return {x:bounds.x, y:bounds.y, width:bounds.width, height:bounds.height};
        }

        private function loadOriginalLogin(event:Event):void {
            originalPreloader.contentLoaderInfo.removeEventListener(Event.COMPLETE, loadOriginalLogin);
            gameLoader.contentLoaderInfo.addEventListener(Event.COMPLETE, startOriginalLogin);
            gameLoader.load(new URLRequest("/Swf/Login.swf"), new LoaderContext(false, ApplicationDomain.currentDomain));
        }

        public function showOriginalLoading(visible:Boolean):void {
            originalPreloader.visible = visible;
            gameLoader.visible = !visible;
            gameLoader.mouseChildren = !visible;
            gameLoader.mouseEnabled = !visible;
        }

        private function startOriginalLogin(event:Event):void {
            gameLoader.contentLoaderInfo.removeEventListener(Event.COMPLETE, startOriginalLogin);
            var cookiesClass:Class = gameLoader.contentLoaderInfo.applicationDomain.getDefinition("worlds4u.model.CookiesDataManager") as Class;
            cookieManager = Object(cookiesClass).getInstance();
            seedRemembered(ExternalInterface.call("getRememberedMogobes") as Array);
            var registered:Object = ExternalInterface.call("getRegistrationMogobe");
            if (registered != null && String(registered) != "") {
                registrationUser = String(registered);
                registrationPending = true;
            }
            Object(gameLoader.content).init();
        }

        public function finishRegistrationLogin(success:Boolean):void {
            if (!success) registrationPending = false;
        }

        private function seedRemembered(accounts:Array):void {
            if (accounts == null || cookieManager == null) return;
            var data:Object = {userName:"", password:"", saveUserName:true, savePassword:false, lang:5};
            var names:Array = [];
            displayNames = {};
            for (var i:int = 0; i < accounts.length && i < 6; i++) {
                var account:Object = accounts[i];
                displayNames["$" + String(account.username).toLowerCase()] = String(account.username);
                // Original LoginDataManager lowercases names and compares them case-sensitively.
                data["userName" + i] = String(account.username).toLowerCase();
                data["userColour" + i] = account.color_id;
                data["saveData" + i] = true;
                data["savePassword" + i] = Boolean(account.has_session);
                // This is a non-secret marker. Session tokens never enter Flash/JS.
                data["userPassword" + i] = account.has_session ? "__MOGOBE_SAVED_SESSION__" : "";
                data["itemsIdList" + i] = "";
                names.push(String(account.username).toLowerCase());
            }
            rememberedNames = names.join("|");
            cookieManager.deleteObject("loginInfo");
            cookieManager.setObject("loginInfo", data);
        }

        public function refreshRememberedState(accounts:Array):void {
            seedRemembered(accounts);
            if (currentLogin == null || loginKind != "saved") return;
            var holder:DisplayObjectContainer = findNamed(currentLogin, "mcBigPreviewHolderInst", 0) as DisplayObjectContainer;
            var password:TextField = findNamed(currentLogin, "txtMultiLoginPassword", 0) as TextField;
            if (holder == null || password == null) return;
            var name:TextField = findNamed(holder, "txtNameSmall", 0) as TextField;
            if (name == null) return;
            for each (var account:Object in accounts) {
                if (String(account.username).toLowerCase() == name.text.toLowerCase() && !account.has_session && password.text == "__MOGOBE_SAVED_SESSION__") {
                    password.text = "";
                }
            }
        }

        private function onLoginRequested(event:Event):void {
            serversPresence = [];
            var info:Object = Object(currentLogin).loginInfo;
            worldLoginInfo = info;
            ExternalInterface.call("onMogobeLoginPreferences", String(info.userName), Boolean(info.saveUserName), Boolean(info.savePassword));
            // Original Login.setCookies runs after success. Never persist its raw password.
            info.savePassword = false;
        }

        private function onWorldSelected(event:Event):void {
            beginWorld();
        }

        public function beginWorld():void {
            if (worldLoginInfo != null) worldLoginInfo.password = "__MOGOBE_CURRENT_SESSION__";
            worldStarting = true;
            showOriginalLoading(true);
        }

        public function getWorldAvatar():Object {
            if (worldAvatar == null) return null;
            return {x:worldAvatar.x, y:worldAvatar.y, visible:worldAvatar.visible, colorId:Object(worldAvatar).Color, action:Object(worldAvatar).currentAction, type:getQualifiedClassName(worldAvatar)};
        }

        public function getWorldAvatars():Array {
            var result:Array = [];
            if (worldAvatar == null || worldAvatar.parent == null) return result;
            var holder:DisplayObjectContainer = worldAvatar.parent;
            for (var i:int = 0; i < holder.numChildren; i++) {
                var avatar:DisplayObject = holder.getChildAt(i);
                var type:String = getQualifiedClassName(avatar);
                if (type != "worlds4u.view.avatar::MyAvatar" && type != "worlds4u.view.avatar::AvatarDocView") continue;
                var balloon:DisplayObject = (avatar as DisplayObjectContainer).getChildByName("speakBallon");
                var text:String = "";
                if (balloon != null) text = collectText(balloon);
                result.push({id:int(avatar.name), x:avatar.x, y:avatar.y, colorId:Object(avatar).Color, action:Object(avatar).currentAction, me:avatar == worldAvatar, speech:text,
                    balloonType:balloon == null ? "" : getQualifiedClassName(balloon),
                    balloonLabel:balloon is MovieClip ? MovieClip(balloon).currentLabel : "",
                    balloonChildren:balloon is DisplayObjectContainer ? childTypes(balloon as DisplayObjectContainer) : []});
            }
            return result;
        }

        private function collectServerRows(node:DisplayObject, rows:Array):void {
            if (node == null || !node.visible) return;
            if (getQualifiedClassName(node) == "mlServer") {
                rows.push(node);
                return;
            }
            var holder:DisplayObjectContainer = node as DisplayObjectContainer;
            for (var i:int = 0; holder != null && i < holder.numChildren; i++) collectServerRows(holder.getChildAt(i),rows);
        }

        public function setServerPresence(servers:Array):void {
            serversPresence = servers;
            updateServerPresence();
        }

        private function updateServerPresence():void {
            if (loginKind != "servers" || hookedServers == null || hookedServers.stage == null) return;
            var rows:Array = [];
            collectServerRows(hookedServers,rows);
            for (var i:int = 0; i < rows.length && i < serversPresence.length; i++) {
                var row:Object = rows[i];
                var data:Object = serversPresence[i];
                row.mcOnLineFriends.gotoAndStop(int(data.friends)>0 ? "YES" : "NO");
                var fill:int = Math.ceil(Number(data.percentage)/20);
                for (var j:int = 1; j <= 5; j++) {
                    row["mcIndOn"+j].visible = j <= fill;
                    row["mcIndOff"+j].visible = j > fill;
                }
                row.mogobePopulation = int(data.online);
                row.mogobeFriends = int(data.friends);
                row.mogobeServerId = int(data.id);
            }
        }

        public function getServerInfo():Array {
            var result:Array = [];
            if (loginKind != "servers") return result;
            var rows:Array = [];
            collectServerRows(hookedServers,rows);
            for each (var row:Object in rows) {
                var fill:int = 0;
                for (var i:int = 1; i <= 5; i++) if (row["mcIndOn"+i].visible) fill++;
                var label:TextField = row.getChildByName("mogobeOnlineCount") as TextField;
                result.push({id:row.mogobeServerId,name:row.txtName.text,online:row.mogobePopulation,
                    friends:row.mogobeFriends,friendIcon:row.mcOnLineFriends.currentLabel,
                    fill:fill,text:label == null ? "" : label.text});
            }
            return result;
        }

        private function collectText(node:DisplayObject):String {
            if (!node.visible) return "";
            if (node is TextField) return TextField(node).text;
            var text:String = "";
            var container:DisplayObjectContainer = node as DisplayObjectContainer;
            if (container != null) for (var i:int = 0; i < container.numChildren; i++) text += collectText(container.getChildAt(i));
            return text;
        }

        private function currentPopup():Object {
            if (mainClip == null) return null;
            var managerClass:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.view.popups.PopupsManeger") as Class;
            var popup:Object = Object(managerClass).getInstance().CurrentPopup;
            if (popup != null && popup.baseView.stage != null && socialPopupStack.indexOf(popup) == -1) socialPopupStack.push(popup);
            for (var i:int = socialPopupStack.length-1; i >= 0; i--) {
                if (socialPopupStack[i].baseView.stage == null) socialPopupStack.splice(i,1);
            }
            if (popup != null && popup.baseView.stage != null) return popup;
            return socialPopupStack.length == 0 ? null : socialPopupStack[socialPopupStack.length-1];
        }

        private function currentProfile():Object {
            var popup:Object = currentPopup();
            return popup != null && (popup.PopupId == 7 || popup.PopupId == 8) ? popup : null;
        }

        public function setSocialState(state:Object):void {
            socialState = {};
            for each (var name:String in state.muted_names) socialState["$"+name] = true;
            var offer:MovieClip = findNamed(mainClip,"btnBodyOffer",0) as MovieClip;
            if (offer != null) {
                offer.visible = int(state.pending_requests) > 0;
                if ("txtBodyOffers" in offer) offer.txtBodyOffers.text = String(state.pending_requests);
            }
        }

        private function displayedMute(name:String):Boolean {
            var pending:Object = pendingMutes["$"+name];
            return pending == null ? socialState["$"+name] == true : Boolean(pending.muted);
        }

        private function inside(node:DisplayObject, parent:DisplayObject):Boolean {
            while (node != null) {
                if (node == parent) return true;
                node = node.parent;
            }
            return false;
        }

        private function socialClick(event:MouseEvent):void {
            clearFriendHover();
            var popup:Object = currentProfile();
            if (popup == null || popup.PopupId != 8) return;
            var button:DisplayObject = findNamed(popup.baseView,"btnBend",0);
            if (!inside(event.target as DisplayObject,button)) return;
            var nick:TextField = profileField(popup.baseView,"txtName");
            if (nick == null || nick.text == "") return;
            event.preventDefault();
            event.stopImmediatePropagation();
            var muted:Boolean = !displayedMute(nick.text);
            var sequence:int = ++muteSequence;
            pendingMutes["$"+nick.text] = {muted:muted, sequence:sequence};
            updateProfileCounters();
            ExternalInterface.call("onMogobeMuteChanged",nick.text,muted,sequence);
        }

        public function finishMuteChange(name:String, sequence:int, success:Boolean, muted:Boolean):void {
            if (success) socialState["$"+name] = muted;
            var pending:Object = pendingMutes["$"+name];
            if (pending == null || int(pending.sequence) != sequence) return;
            delete pendingMutes["$"+name];
            updateProfileCounters();
            var popup:Object = currentProfile();
            if (popup == null || popup.PopupId != 8) return;
            var nick:TextField = profileField(popup.baseView,"txtName");
            if (nick != null && nick.text == name) {
                // Ask through the original controller so its private Button
                // wrappers also refresh permission-dependent buttons.
                var cls:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.events.AvatarEvent") as Class;
                popup.dispatchEvent(new cls(Object(cls).ASK_DATA_EVT,"user__getUserCardInfo",{userName:name,userId:popup.Data.userId},-1));
            }
        }

        public function chooseOriginalServer():Boolean {
            if (loginKind != "servers" || hookedServers == null || hookedServers.stage == null) return false;
            var rows:Array = [];
            collectServerRows(hookedServers,rows);
            if (rows.length == 0) return false;
            rows[0].dispatchEvent(new MouseEvent(MouseEvent.CLICK,true));
            return true;
        }

        private function friendControl(node:DisplayObject):Object {
            var popup:Object = currentPopup();
            if (popup == null || popup.PopupId != 24 || !inside(node,popup.baseView)) return null;
            while (node != null && node != popup.baseView) {
                var id:int = 0;
                var section:String = "BuddyList";
                var type:String = getQualifiedClassName(node);
                if (node.name == "btnClose") { id = 3; section = "Buttons"; }
                else if (node.name == "btnBuddyTab") id = 1;
                else if (node.name == "btnIgnorTab") id = 2;
                else if (node.name == "btnRequestTab") id = 3;
                else if (type == "mlUserOnLine" || type == "mlUserOffline") id = 4;
                else if (type == "btnAddBuddy") id = 5;
                else if (type == "btnRemoveBuddy") {
                    var line:DisplayObject = node.parent;
                    while (line != null && !("buddy" in Object(line))) line = line.parent;
                    var status:int = line == null ? 2 : Object(line).buddy.Status;
                    id = status == 1 ? 6 : status == 3 ? 10 : 8;
                }
                else if (type == "btnBestBuddy") {
                    var owner:DisplayObject = node.parent;
                    while (owner != null && !("buddy" in Object(owner))) owner = owner.parent;
                    id = owner != null && Object(owner).buddy.Status == 4 ? 11 : 7;
                }
                if (id != 0) {
                    var language:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.model.LanguageManager") as Class;
                    return {clip:node, text:Object(language).getInstance().getMessage(id,section)};
                }
                node = node.parent;
            }
            return null;
        }

        private function hoverFrame(clip:MovieClip, label:String):void {
            if (clip == null || clip.currentLabel == "GREYOUT") return;
            for each (var frame:Object in clip.currentLabels) if (frame.name == label) {
                clip.gotoAndStop(label);
                return;
            }
        }

        private function friendMouseOver(event:MouseEvent):void {
            var descriptor:Object = friendControl(event.target as DisplayObject);
            if (descriptor == null) return;
            event.stopImmediatePropagation();
            if (friendHover == descriptor.clip) return;
            clearFriendHover();
            friendHover = descriptor.clip as MovieClip;
            friendHoverText = String(descriptor.text);
            friendHoverTime = getTimer();
            hoverFrame(friendHover,"OVER");
            refreshFriendsFonts();
        }

        private function friendMouseOut(event:MouseEvent):void {
            var descriptor:Object = friendControl(event.target as DisplayObject);
            if (descriptor == null) return;
            event.stopImmediatePropagation();
            if (friendHover != null && inside(event.relatedObject as DisplayObject,friendHover)) return;
            clearFriendHover();
            refreshFriendsFonts();
        }

        private function clearFriendHover():void {
            hoverFrame(friendHover,"OUT");
            friendHover = null;
            friendHoverText = "";
            if (friendTooltip != null && friendTooltip.parent != null) friendTooltip.parent.removeChild(friendTooltip);
            friendTooltip = null;
        }

        private function updateFriendTooltip():void {
            var popup:Object = currentPopup();
            if (friendHover == null) return;
            if (friendHover.stage == null || popup == null || popup.PopupId != 24 ||
                !inside(friendHover,popup.baseView) || !friendHover.hitTestPoint(stage.mouseX,stage.mouseY,true)) {
                clearFriendHover();
                return;
            }
            if (friendTooltip != null || getTimer()-friendHoverTime < 800) return;
            // Match original AltPopUp's white box and Arial 10, while keeping
            // it out of hit testing and disposing it with the hovered control.
            var text:TextField = new TextField();
            text.defaultTextFormat = new TextFormat("Arial",10,0,false,false,false,null,null,TextFormatAlign.CENTER);
            text.embedFonts = true;
            text.text = friendHoverText;
            text.width = text.textWidth+6;
            text.height = text.textHeight+4;
            text.selectable = false;
            friendTooltip = new Sprite();
            friendTooltip.mouseEnabled = false;
            friendTooltip.mouseChildren = false;
            friendTooltip.graphics.lineStyle(0,0);
            friendTooltip.graphics.beginFill(0xFFFFFF);
            friendTooltip.graphics.drawRect(0,0,text.width,text.height);
            friendTooltip.graphics.endFill();
            friendTooltip.addChild(text);
            friendTooltip.x = Math.max(0,Math.min(768-text.width,mouseX-text.width/2));
            friendTooltip.y = mouseY-text.height-10 > 0 ? mouseY-text.height-10 : mouseY+16;
            addChild(friendTooltip);
        }

        public function getFriendsTooltipInfo():Object {
            return {visible:friendTooltip != null,text:friendTooltip == null ? "" : collectText(friendTooltip)};
        }

        private function childTypes(holder:DisplayObjectContainer):Array {
            var result:Array = [];
            for (var i:int = 0; i < holder.numChildren; i++) result.push(getQualifiedClassName(holder.getChildAt(i)));
            return result;
        }

        public function getWorldCursor():Object {
            var cursor:DisplayObject = stage.getChildByName("MouseCursor");
            if (cursor == null) return null;
            return {type:getQualifiedClassName(cursor),x:cursor.x,y:cursor.y};
        }

        public function getWorldEffects():Array {
            var result:Array = [];
            if (worldAvatar == null || worldAvatar.parent == null) return result;
            var holder:DisplayObjectContainer = worldAvatar.parent;
            for (var i:int = 0; i < holder.numChildren; i++) {
                var child:DisplayObject = holder.getChildAt(i);
                var type:String = getQualifiedClassName(child);
                if (type.indexOf("mlIco_") == 0) result.push({type:type, x:child.x, y:child.y});
            }
            return result;
        }

        public function getSocialPopupInfo():Object {
            var popup:Object = currentPopup();
            if (popup == null) return null;
            var rows:Array = [];
            var holder:DisplayObjectContainer = findNamed(popup.baseView,"mcListPlaceHolder",0) as DisplayObjectContainer;
            if (popup.PopupId == 24 && holder != null && holder.numChildren > 0) {
                var list:DisplayObjectContainer = holder.getChildAt(0) as DisplayObjectContainer;
                for (var i:int = 0; list != null && i < list.numChildren; i++) {
                    var row:Object = list.getChildAt(i);
                    if ("buddy" in row) rows.push({userName:row.buddy.BuddyName, status:row.buddy.Status,
                        serverName:row.buddy.ServerName, text:collectText(row as DisplayObject)});
                }
            }
            return {popupId:popup.PopupId, rows:rows};
        }

        public function getSocialRowControlBounds(name:String, action:String):Object {
            var popup:Object = currentPopup();
            if (popup == null || popup.PopupId != 24) return null;
            var row:DisplayObjectContainer = findNamed(popup.baseView,name,0) as DisplayObjectContainer;
            if (row == null) return null;
            var holderName:String = action == "name" ? "mcNameHolder" : action == "primary" ? "mcBtnHolder1" : "mcBtnHolder2";
            var holder:DisplayObjectContainer = row.getChildByName(holderName) as DisplayObjectContainer;
            if (holder == null || holder.numChildren == 0) return null;
            var bounds:Rectangle = holder.getChildAt(0).getBounds(this);
            return {x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height};
        }

        private function renderFriendField(view:Object, key:String, name:String, value:String):void {
            var original:TextField = view[key] as TextField;
            var rendered:TextField = view.getChildByName(name) as TextField;
            if (rendered == null && original != null && original.parent != null) {
                var fonts:Class = ApplicationDomain.currentDomain.getDefinition("FontClass") as Class;
                rendered = Object(fonts).getInstance().addText(original,value);
                rendered.name = name;
                rendered.mouseEnabled = false;
            }
            // OVER/OUT frames recreate the movie's sample text. Keep the
            // persistent embedded-font label and suppress each new sample.
            if (original != null && original != rendered && original.parent != null) original.visible = false;
            if (rendered != null && rendered.text != value) rendered.text = value;
        }

        private function refreshFriendsFonts():void {
            var popup:Object = currentPopup();
            if (popup == null || popup.PopupId != 24) return;
            var holder:DisplayObjectContainer = findNamed(popup.baseView,"mcListPlaceHolder",0) as DisplayObjectContainer;
            if (holder == null || holder.numChildren == 0) return;
            var list:DisplayObjectContainer = holder.getChildAt(0) as DisplayObjectContainer;
            for (var i:int = 0; list != null && i < list.numChildren; i++) {
                var row:Object = list.getChildAt(i);
                if (!("buddy" in row) || !("mcNameHolder" in row) || row.mcNameHolder.numChildren == 0) continue;
                var nameView:Object = row.mcNameHolder.getChildAt(0);
                renderFriendField(nameView,"txtName","mogobeBuddyName",String(row.buddy.BuddyName));
                renderFriendField(nameView,"txtServer","mogobeBuddyServer",row.buddy.ServerName == null ? "" : String(row.buddy.ServerName));
                // Offline OVER uses a different timeline text instance on its
                // first visit. Its public txtName reference may still point at
                // OUT, so suppress all authored samples, not just that reference.
                for (var j:int = 0; j < nameView.numChildren; j++) {
                    var sample:TextField = nameView.getChildAt(j) as TextField;
                    if (sample != null && sample.name != "mogobeBuddyName" && sample.name != "mogobeBuddyServer") sample.visible = false;
                }
            }
        }

        private function hideLuxuryCurrency(view:DisplayObjectContainer):void {
            var amount:TextField = profileField(view,"txtAmount_2");
            if (amount != null) amount.visible = false;
            // The original p_7 places the separate blue currency icon at
            // (303,338.5), sprite 146. Hide the complete sprite, including shadow.
            for (var i:int = 0; i < view.numChildren; i++) {
                var child:DisplayObject = view.getChildAt(i);
                if (Math.abs(child.x-303)<0.2 && Math.abs(child.y-338.5)<0.2 && child.width<40 && child.height<40) child.visible = false;
                // Original shape 144 contains all five counter pictograms.
                // Keep the original vector paths and isolate the four used
                // icons with masks, then center each over its own counter.
                var bounds:Rectangle = child.getBounds(view);
                if (child is Shape && child != Object(view).mogobeProfileIconSource &&
                    Math.abs(bounds.x-159.9)<0.2 && Math.abs(bounds.y-337.5)<0.2 && Math.abs(bounds.width-170)<0.2 &&
                    Object(view).mogobeProfileIconsPrepared != true && profileIconDomain != null) {
                    Object(view).mogobeProfileIconSource = child;
                    child.visible = false;
                    Object(view).mogobeProfileIconsPrepared = true;
                    var cuts:Array = [159.9,190,225,261,296];
                    var authored:Array = [168.9,203.4,239.4,275.4];
                    var targets:Array = [182.125,218.125,254.125,290.125];
                    for (var iconIndex:int = 0; iconIndex < 4; iconIndex++) {
                        var holder:Sprite = new Sprite();
                        holder.name = "mogobeProfileIcon"+iconIndex;
                        holder.mouseEnabled = false;
                        holder.mouseChildren = false;
                        var iconClass:Class = profileIconDomain.getDefinition("MogobeProfileCounterArtwork") as Class;
                        var icon:DisplayObject = new iconClass() as DisplayObject;
                        holder.addChild(icon);
                        var iconMask:Shape = new Shape();
                        iconMask.graphics.beginFill(0);
                        iconMask.graphics.drawRect(cuts[iconIndex],330,cuts[iconIndex+1]-cuts[iconIndex],32);
                        iconMask.graphics.endFill();
                        holder.addChild(iconMask);
                        icon.mask = iconMask;
                        holder.x = targets[iconIndex]-authored[iconIndex];
                        view.addChild(holder);
                    }
                }
            }
            var keys:Array = ["txtNewMsgs","txtFriends","txtAge","txtAmount_1"];
            var centers:Array = [182.125,218.125,254.125,290.125];
            for (var j:int = 0; j < keys.length; j++) {
                var field:TextField = profileField(view,keys[j]);
                // Wait for the original FontClass replacement; moving the
                // authored source would confuse its controller's own layout.
                if (field == null || field == Object(view)[keys[j]]) continue;
                var format:TextFormat = field.defaultTextFormat;
                format.align = TextFormatAlign.CENTER;
                format.leftMargin = 0;
                format.rightMargin = 0;
                format.indent = 0;
                field.defaultTextFormat = format;
                field.setTextFormat(format);
                var rect:Rectangle = field.getBounds(view);
                field.x += Number(centers[j])-rect.x-rect.width/2;
            }
        }

        private function profileField(view:DisplayObjectContainer, key:String):TextField {
            if (!(key in Object(view))) return null;
            var named:TextField = view.getChildByName("mogobeProfile_"+key) as TextField;
            if (named != null) return named;
            var source:TextField = Object(view)[key] as TextField;
            if (source == null) return null;
            if (source.parent != null) return source;
            // Original FontClass.addText replaces the source with an unnamed
            // embedded-font TextField. Match the original centered rectangle.
            for (var i:int = 0; i < view.numChildren; i++) {
                var field:TextField = view.getChildAt(i) as TextField;
                if (field != null && Math.abs(field.y - source.y) < 1 &&
                    Math.abs(field.x + field.width / 2 - source.x - source.width / 2) < 2) {
                    field.name = "mogobeProfile_"+key;
                    return field;
                }
            }
            return null;
        }

        private function updateProfileCounters():void {
            var popup:Object = currentProfile();
            if (popup == null) return;
            var targetId:int = int(popup.Data.userId);
            var targetName:String = popup.Data.userName == null ? "" : String(popup.Data.userName);
            var targetKey:String = targetId > 0 ? "id:"+targetId : targetName;
            if (targetKey != "" && Object(popup.baseView).mogobeProfileRequestedKey != targetKey) {
                Object(popup.baseView).mogobeProfileRequestedKey = targetKey;
                ExternalInterface.call("onMogobeProfileShown");
            }
            if (Number(Object(popup.baseView).mogobeScoreValue) >= 1024000) {
                var maxIndicator:MovieClip = popup.baseView.getChildByName("mogobeLevelIndicator") as MovieClip;
                if (maxIndicator != null) {
                    maxIndicator.gotoAndStop("ScoreLevel_11");
                    var maxFill:MovieClip = findNamed(maxIndicator,"mc",0) as MovieClip;
                    if (maxFill != null) maxFill.gotoAndStop(maxFill.totalFrames);
                }
            }
            var adminMark:DisplayObject = findNamed(popup.baseView,"mcMember",0);
            if (adminMark != null) {
                if (adminMark is flash.display.InteractiveObject) flash.display.InteractiveObject(adminMark).mouseEnabled = false;
                if (adminMark is DisplayObjectContainer) DisplayObjectContainer(adminMark).mouseChildren = false;
            }
            if (popup.PopupId == 7) {
                hideLuxuryCurrency(popup.baseView);
                var view:Object = popup.baseView;
                if (view.mogobeProfilePreparing == true) {
                    var coins:TextField = profileField(popup.baseView,"txtAmount_1");
                    if (coins != null && coins != view.txtAmount_1 && view.mogobeProfileIconsPrepared == true) {
                        view.mogobeProfilePreparing = false;
                        view.visible = true;
                    }
                }
            }
            if (popup.PopupId == 8) {
                var nick:TextField = profileField(popup.baseView,"txtName");
                var mute:MovieClip = findNamed(popup.baseView,"btnBend",0) as MovieClip;
                if (nick != null && mute != null) mute.gotoAndStop(displayedMute(nick.text) ? "CHEKED" : "UNCHECKED");
            }
            if (worldAvatar == null || worldAvatar.parent == null) return;
            var holder:DisplayObjectContainer = worldAvatar.parent;
            for (var i:int = 0; i < holder.numChildren; i++) {
                var avatar:DisplayObject = holder.getChildAt(i);
                if (int(avatar.name) != int(popup.Data.userId)) continue;
                var type:String = getQualifiedClassName(avatar);
                if (type != "worlds4u.view.avatar::MyAvatar" && type != "worlds4u.view.avatar::AvatarDocView") continue;
                var user:Object = Object(avatar).User;
                var age:TextField = profileField(popup.baseView, "txtAge");
                var friends:TextField = profileField(popup.baseView, "txtFriends");
                if (age != null && age.text != String(user.getVaribale("age"))) age.text = String(user.getVaribale("age"));
                if (friends != null && friends.text != String(user.getVaribale("friends"))) friends.text = String(user.getVaribale("friends"));
                return;
            }
        }

        private function experienceLevel(score:int):int {
            var thresholds:Array = [1000,2000,4000,8000,16000,32000,64000,124000,256000,512000,1024000];
            var level:int = 1;
            for each (var threshold:int in thresholds) if (score >= threshold) level++;
            return level;
        }

        public function setProfileProgress(data:Object):void {
            var popup:Object = currentProfile();
            if (popup == null || profileIconDomain == null) return;
            var targetId:int = int(popup.Data.userId);
            if (targetId > 0 && targetId != int(data.userId)) return;
            if (targetId <= 0 && String(popup.Data.userName).toLowerCase() != String(data.userName).toLowerCase()) return;
            var view:Object = popup.baseView;
            view.mogobeProfileUserId = int(data.userId);
            var admin:DisplayObject = findNamed(popup.baseView,"mcMember",0);
            if (admin != null) admin.visible = Boolean(data.isAdmin);
            var score:int = int(data.score);
            if (view.mogobeScoreValue === score) return;
            var original:MovieClip = findNamed(popup.baseView,"mcScore",0) as MovieClip;
            if (original == null) return;
            original.visible = false;
            original.mouseEnabled = false;
            original.mouseChildren = false;
            var indicator:MovieClip = popup.baseView.getChildByName("mogobeLevelIndicator") as MovieClip;
            if (indicator == null) {
                var cls:Class = profileIconDomain.getDefinition("MogobeScoreIndicator") as Class;
                indicator = new cls() as MovieClip;
                indicator.name = "mogobeLevelIndicator";
                indicator.transform.matrix = original.transform.matrix;
                popup.baseView.addChild(indicator);
                indicator.addEventListener(Event.REMOVED_FROM_STAGE,function(event:Event):void {
                    if (view.mogobeExperienceController != null) view.mogobeExperienceController.disableEvents();
                });
            }
            if (view.mogobeExperienceController != null) view.mogobeExperienceController.disableEvents();
            cls = ApplicationDomain.currentDomain.getDefinition("worlds4u.view.UserExperience") as Class;
            view.mogobeExperienceController = new cls(indicator,score);
            if (score >= 1024000) {
                indicator.gotoAndStop("ScoreLevel_11");
                var fill:MovieClip = findNamed(indicator,"mc",0) as MovieClip;
                if (fill != null) fill.gotoAndStop(fill.totalFrames);
            }
            view.mogobeScoreValue = score;
        }

        public function getExperienceInfo():Object {
            return {shown:scoreSignsShown,last:lastScoreSign};
        }

        public function getProfileInfo():Object {
            var popup:Object = currentProfile();
            if (popup == null) return null;
            var view:DisplayObjectContainer = popup.baseView;
            var nick:TextField = profileField(view, "txtName");
            var age:TextField = profileField(view, "txtAge");
            var friends:TextField = profileField(view, "txtFriends");
            var inventory:String = "";
            if ("mcAvatarInventory" in Object(view) && Object(view).mcAvatarInventory != null) inventory = Object(view).mcAvatarInventory.mcTabs.currentLabel;
            var counters:Array = [];
            for each (var key:String in ["txtNewMsgs","txtFriends","txtAge","txtAmount_1"]) {
                var counter:TextField = profileField(view,key);
                if (counter == null) continue;
                var rect:Rectangle = counter.getBounds(view);
                counters.push({name:key,center:rect.x+rect.width/2,align:counter.defaultTextFormat.align});
            }
            var iconBoxes:Array = [];
            for (var iconIndex:int = 0; iconIndex < 4; iconIndex++) {
                var holder:DisplayObjectContainer = view.getChildByName("mogobeProfileIcon"+iconIndex) as DisplayObjectContainer;
                if (holder != null && holder.numChildren == 2) {
                    var box:Rectangle = holder.getChildAt(1).getBounds(this);
                    iconBoxes.push({x:box.x,y:box.y,width:box.width,height:box.height});
                }
            }
            var luxuryIconVisible:Boolean = false;
            for (var i:int = 0; i < view.numChildren; i++) {
                var child:DisplayObject = view.getChildAt(i);
                if (Math.abs(child.x-303)<0.2 && Math.abs(child.y-338.5)<0.2 && child.width<40 && child.height<40 && child.visible) luxuryIconVisible = true;
            }
            var langClass:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.model.LanguageManager") as Class;
            var numericLevel:int = experienceLevel(int(Object(view).mogobeScoreValue));
            return {levelName:Object(langClass).getInstance().getMessage(numericLevel == 12 ? 0 : numericLevel,"UserExperience"),score:Object(view).mogobeScoreValue,level:numericLevel,iconBoxes:iconBoxes,visible:view.visible,counters:counters,luxuryIconVisible:view.visible && luxuryIconVisible,popupId:popup.PopupId, userId:Object(view).mogobeProfileUserId == null ? int(popup.Data.userId) : int(Object(view).mogobeProfileUserId), userName:popup.Data.userName != null ? String(popup.Data.userName) : nick == null ? "" : nick.text,
                days:age == null ? "" : age.text, friends:friends == null ? "" : friends.text, inventory:inventory,
                adminBadge:findNamed(view,"mcMember",0) != null && findNamed(view,"mcMember",0).visible,
                muted:nick != null && displayedMute(nick.text),
                mutePending:nick != null && pendingMutes["$"+nick.text] != null,
                muteFrame:findNamed(view,"btnBend",0) is MovieClip ? MovieClip(findNamed(view,"btnBend",0)).currentLabel : "",
                luxuryVisible:view.visible && profileField(view,"txtAmount_2") != null && profileField(view,"txtAmount_2").visible};
        }

        public function getProfileControlBounds(name:String):Object {
            var popup:Object = currentPopup();
            if (popup == null) return null;
            var control:DisplayObject = findNamed(popup.baseView, name, 0);
            if (control == null) return null;
            var bounds:Rectangle = control.getBounds(this);
            return {x:bounds.x, y:bounds.y, width:bounds.width, height:bounds.height};
        }

        private function avatarCameraClick(event:MouseEvent):void {
            var popup:Object = currentProfile();
            if (popup == null || popup.PopupId != 7) return;
            var camera:DisplayObject = findNamed(popup.baseView,"btnCamera",0);
            var target:DisplayObject = event.target as DisplayObject;
            while (target != null && target != camera) target = target.parent;
            if (target == null) return;
            event.stopImmediatePropagation();
            event.preventDefault();
            try {
                var holder:DisplayObjectContainer = findNamed(popup.baseView,"mcAvatarHolder",0) as DisplayObjectContainer;
                var avatar:DisplayObject = findAvatarPortrait(holder);
                if (avatar == null) return;
                var bounds:Rectangle = avatar.getBounds(avatar);
                var scale:Number = 2;
                var image:BitmapData = new BitmapData(Math.ceil(bounds.width*scale)+24,Math.ceil(bounds.height*scale)+24,false,0xFFFFFF);
                image.draw(avatar,new Matrix(scale,0,0,scale,12-bounds.x*scale,12-bounds.y*scale));
                var encoder:Class = ApplicationDomain.currentDomain.getDefinition("com.adobe.images.JPGEncoder") as Class;
                var bytes:ByteArray = new encoder(90).encode(image);
                image.dispose();
                ExternalInterface.call("onMogobeAvatarPhoto",encodePhoto(bytes));
            } catch(error:Error) { ExternalInterface.call("showMogobePopup","Не удалось получить изображение могоби: "+error.message); }
        }

        private function findAvatarPortrait(node:DisplayObject):DisplayObject {
            if (node == null) return null;
            if (getQualifiedClassName(node) == "mlCardAvatar") return node;
            var holder:DisplayObjectContainer = node as DisplayObjectContainer;
            for (var i:int=0;holder != null && i<holder.numChildren;i++) {
                var result:DisplayObject = findAvatarPortrait(holder.getChildAt(i));
                if (result != null) return result;
            }
            return null;
        }

        private function encodePhoto(bytes:ByteArray):String {
            var alphabet:String="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
            var result:String="";
            bytes.position=0;
            while(bytes.bytesAvailable>0) {
                var a:int=bytes.readUnsignedByte();
                var b:int=bytes.bytesAvailable>0?bytes.readUnsignedByte():-1;
                var c:int=bytes.bytesAvailable>0?bytes.readUnsignedByte():-1;
                result+=alphabet.charAt(a>>2)+alphabet.charAt(((a&3)<<4)|(b<0?0:b>>4));
                result+=b<0?"=":alphabet.charAt(((b&15)<<2)|(c<0?0:c>>6));
                result+=c<0?"=":alphabet.charAt(c&63);
            }
            return result;
        }

        private function originalDisplayAdded(event:Event):void {
            var view:DisplayObject = event.target as DisplayObject;
            prepareRoomView(view);
            if (view != null && getQualifiedClassName(view) == "mlWorldScoreSign") {
                scoreSignsShown++;
                lastScoreSign = collectText(view);
            }
            if (view is DisplayObjectContainer && getQualifiedClassName(view) == "mlPopup_33") prepareShopLayout(view as DisplayObjectContainer);
            if (view != null && getQualifiedClassName(view) == "mlPopup_3") {
                // Hold the original popup before its first paint until the
                // cached island/button have been attached in this same frame.
                view.visible = false;
            }
            if (view != null && getQualifiedClassName(view) == "mlPopup_7") {
                // The asynchronous asset loader can draw this card before the
                // next timeline tick. Do not expose its unadapted first frame.
                view.visible = false;
                Object(view).mogobeProfilePreparing = true;
            }
        }

        private function prepareRoomView(view:DisplayObject):void {
            if (view == null || getQualifiedClassName(view) != "mlMagicForest" || Object(view).mogobeExitsPrepared) return;
            var entry:MovieClip = findNamed(view,"mcEntryPoint_440",0) as MovieClip;
            if (entry == null) return;
            // The original MagicForest[4] leaves this tree-door hit zone above
            // the stage. Preserve the original shape and restore its position.
            // Server geometry uses the same ENTRY_POSITIONS in the generator.
            // Include the front landing: the tree roots clip walks aimed at
            // the door itself, so the trigger must reach the accessible step.
            entry.x = 100;
            entry.y = 330;
            Object(view).mogobeExitsPrepared = true;
        }

        private function finishOriginalFrame(event:Event):void {
            if (mainClip == null) return;
            refreshFriendsFonts();
            updateProfileCounters();
            updateWorldPanel();
            updateShopLayout();
            updateWorldMap();
        }

        private function preloadProfileIcons():void {
            if (profileIconLoader != null) return;
            profileIconLoader = new Loader();
            profileIconLoader.contentLoaderInfo.addEventListener(Event.COMPLETE,function(event:Event):void {
                profileIconDomain = profileIconLoader.contentLoaderInfo.applicationDomain;
                updateProfileCounters();
            });
            profileIconLoader.load(new URLRequest("/compat/ProfileCounterIcons.swf"),new LoaderContext(false,new ApplicationDomain()));
        }

        private function preloadWorldMap():void {
            if (mapAssetsLoader != null) return;
            mapAssetsLoader = new Loader();
            mapAssetsLoader.contentLoaderInfo.addEventListener(Event.COMPLETE,function(event:Event):void {
                mapAssetsDomain = mapAssetsLoader.contentLoaderInfo.applicationDomain;
                updateWorldMap();
            });
            mapAssetsLoader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR,function(event:IOErrorEvent):void { mapAssetsError = event.text; });
            mapAssetsLoader.contentLoaderInfo.addEventListener(SecurityErrorEvent.SECURITY_ERROR,function(event:SecurityErrorEvent):void { mapAssetsError = event.text; });
            mapAssetsLoads++;
            mapAssetsLoader.load(new URLRequest("/compat/WorldMapBumagLand.swf"),new LoaderContext(false,new ApplicationDomain()));
        }

        private function updateWorldMap():void {
            var popup:Object = currentPopup();
            if (popup == null || popup.PopupId != 3 || mapAssetsDomain == null) return;
            var view:MovieClip = popup.baseView as MovieClip;
            var map:DisplayObjectContainer = findNamed(view,"mcMap",0) as DisplayObjectContainer;
            if (map == null || Object(view).mogobeMapPrepared) return;
            Object(view).mogobeMapPrepared = true;
            var spaceship:MovieClip = map.getChildByName("mcBumagVale") as MovieClip;
            if (spaceship != null) {
                spaceship.visible = false;
                spaceship.mouseEnabled = false;
                spaceship.mouseChildren = false;
                Object(view).mogobeMapSpaceship = spaceship;
                map.removeChild(spaceship);
            }
            // The old standalone birch (sprite 54 at map depth 499) is next to
            // the imported portal. Match its authored transform, not its name:
            // this timeline object is unnamed and timeline names are read-only.
            for (var i:int = 0; i < map.numChildren; i++) {
                var tree:DisplayObject = map.getChildAt(i);
                var matrix:Matrix = tree.transform.matrix;
                if (Math.abs(matrix.tx-188.1)<0.01 && Math.abs(matrix.ty-52.05)<0.01 &&
                    Math.abs(matrix.a+0.17138671875)<0.00001 && Math.abs(matrix.d-0.1880950927734375)<0.00001) {
                    tree.visible = false;
                    Object(view).mogobeMapBirch = tree;
                    break;
                }
            }
            var fragmentClass:Class = mapAssetsDomain.getDefinition("MogobeBumagMapFragment") as Class;
            var scenery:MovieClip = new fragmentClass() as MovieClip;
            scenery.stop();
            scenery.name = "mogobeBumagIsland";
            scenery.mouseEnabled = false;
            scenery.mouseChildren = false;
            var buttonClip:MovieClip = scenery.getChildByName("mcBumagVale") as MovieClip;
            // Both layers retain the exact transforms from Russian map object
            // 286. No URL load or asynchronous display change happens on open.
            scenery.removeChild(buttonClip);
            map.addChildAt(scenery,0);
            map.addChild(buttonClip);
            var buttonClass:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.common.uiControls.Button") as Class;
            var button:Object = new buttonClass(buttonClip,"Бумагленд",false);
            button.name = "mcBumagVale";
            button.addEventListener(MouseEvent.CLICK,function(click:MouseEvent):void {
                click.stopImmediatePropagation();
                var avatarEvent:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.events.AvatarEvent") as Class;
                var config:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.common.AppConfig") as Class;
                popup.dispatchEvent(new avatarEvent(Object(avatarEvent).AVTARCHANGEROOM_EVT,"rooms__jumpToRoom",
                    {nameId:"BumagVale",userId:Object(config).MySfsUserId,userName:Object(config).MyUserName},-1));
                popup.dispatchEvent(new Event(Event.CLOSE));
                popup.disableEvents();
            });
            buttonClip.addEventListener(Event.REMOVED_FROM_STAGE,function(event:Event):void { button.destroy(); });
            Object(view).mogobeMapReady = true;
            view.visible = true;
        }

        public function getWorldMapInfo():Object {
            var popup:Object = currentPopup();
            if (popup == null || popup.PopupId != 3 || findNamed(popup.baseView,"mcMap",0) == null) return null;
            var button:MovieClip = findNamed(popup.baseView,"mcBumagVale",0) as MovieClip;
            var spaceship:DisplayObject = Object(popup.baseView).mogobeMapSpaceship as DisplayObject;
            var tree:DisplayObject = Object(popup.baseView).mogobeMapBirch as DisplayObject;
            var island:DisplayObject = findNamed(popup.baseView,"mogobeBumagIsland",0);
            return {ready:Object(popup.baseView).mogobeMapReady == true,visible:popup.baseView.visible,
                error:mapAssetsError,assetsReady:mapAssetsDomain != null,assetsLoads:mapAssetsLoads,
                birchFound:tree != null,birchVisible:tree != null && tree.visible,
                buttonClass:button == null ? "" : getQualifiedClassName(button),
                spaceshipVisible:spaceship != null && spaceship.visible,
                islandVisible:island != null && island.visible,
                buttonFrame:button == null ? "" : button.currentLabel,
                buttonFrames:button == null ? 0 : button.totalFrames};
        }

        private function prepareShopLayout(view:DisplayObjectContainer):void {
            if (view == null || Object(view).mogobeShopPrepared == true) return;
            var panel:DisplayObjectContainer = findNamed(view,"mcShop",0) as DisplayObjectContainer;
            if (panel == null) return;
            Object(view).mogobeShopPrepared = true;
            var luxury:DisplayObject = panel.getChildByName("txtAmount_2");
            if (luxury != null) luxury.visible = false;
            var amount:DisplayObject = panel.getChildByName("txtAmount_1");
            var coins:DisplayObject = panel.getChildByName("mcCoinsIcon");
            if (amount != null) amount.y += 20;
            if (coins != null) coins.y += 20;
            for (var i:int = 0; i < panel.numChildren; i++) {
                var child:DisplayObject = panel.getChildAt(i);
                var bounds:Rectangle = child.getBounds(panel);
                // Luxury icon and its authored shadow are separate objects.
                if ((Math.abs(child.x-173.05)<0.2 && Math.abs(child.y-295.85)<0.2) ||
                    (child is Shape && Math.abs(bounds.x-178.4)<0.2 && Math.abs(bounds.y-294.8)<0.2)) child.visible = false;
                if (child is Shape && Math.abs(bounds.x-180.1)<0.2 && Math.abs(bounds.y-267.3)<0.2) child.y += 20;
            }
        }

        private function updateShopLayout():void {
            var popup:Object = currentPopup();
            if (popup != null && getQualifiedClassName(popup.baseView) == "mlPopup_33") prepareShopLayout(popup.baseView);
        }

        private function updateWorldPanel():void {
            var controls:DisplayObject = findNamed(mainClip,"mcControlButtons",0);
            if (controls == null) return;
            var dance:MovieClip = findNamed(controls,"mcDanceMove",0) as MovieClip;
            if (dance != null) {
                dance.visible = false;
                dance.mouseEnabled = false;
                dance.mouseChildren = false;
            }
            var field:TextField = findNamed(findNamed(controls,"mcChat",0),"txtSpeak",0) as TextField;
            if (field == null) return;
            // setTextFormat alone leaves the empty input's default paragraph
            // right-aligned. Apply both so digits and commands also start left.
            var format:TextFormat = field.defaultTextFormat;
            format.align = TextFormatAlign.LEFT;
            format.leftMargin = 0;
            format.rightMargin = 0;
            format.indent = 0;
            field.defaultTextFormat = format;
            field.setTextFormat(format);
            if (field.length == 0) field.scrollH = 0;
        }

        public function getWorldPanelInfo():Object {
            var controls:DisplayObject = findNamed(mainClip,"mcControlButtons",0);
            if (controls == null) return null;
            var field:TextField = findNamed(findNamed(controls,"mcChat",0),"txtSpeak",0) as TextField;
            var dance:DisplayObject = findNamed(controls,"mcDanceMove",0);
            return {text:field == null ? "" : field.text,
                defaultAlign:field == null ? "" : field.defaultTextFormat.align,
                align:field == null ? "" : field.getTextFormat().align,
                danceVisible:dance != null && dance.visible};
        }

        public function getChatMenuItems():Array {
            var result:Array = [];
            collectChatMenuItems(mainClip,result);
            return result;
        }

        private function collectChatMenuItems(node:DisplayObject, result:Array):void {
            if (node == null || !node.visible) return;
            if (getQualifiedClassName(node) == "worlds4u.common.uiControls.menus::MenuItem") {
                var item:Object = Object(node).curr_item;
                var bounds:Rectangle = item.mcHit.getBounds(this);
                result.push({text:collectText(item),x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height});
            }
            var holder:DisplayObjectContainer = node as DisplayObjectContainer;
            if (holder != null) for (var i:int = 0; i < holder.numChildren; i++) collectChatMenuItems(holder.getChildAt(i),result);
        }

        private function worldChat():DisplayObjectContainer {
            if (mainClip == null || worldAvatar == null || lastState.indexOf("world:") != 0) return null;
            var controls:DisplayObject = findNamed(mainClip, "mcControlButtons", 0);
            return findNamed(controls, "mcChat", 0) as DisplayObjectContainer;
        }

        private function consumeChatCommand(event:Event, chat:DisplayObjectContainer):void {
            var field:TextField = findNamed(chat, "txtSpeak", 0) as TextField;
            if (field == null || field.text.replace(/^\s+|\s+$/g, "").toLowerCase() != "/exit") return;
            event.preventDefault();
            event.stopImmediatePropagation();
            field.text = "";
            ExternalInterface.call("onMogobeChatCommand", "exit");
        }

        private function worldChatKey(event:KeyboardEvent):void {
            if (event.keyCode == 116 && mainClip != null && worldAvatar != null) {
                event.preventDefault();
                event.stopImmediatePropagation();
                ExternalInterface.call("onMogobeReconnect");
                return;
            }
            if (event.keyCode != 13) return;
            var chat:DisplayObjectContainer = worldChat();
            if (chat != null && event.target == findNamed(chat, "txtSpeak", 0)) consumeChatCommand(event, chat);
        }

        private function worldChatClick(event:MouseEvent):void {
            var chat:DisplayObjectContainer = worldChat();
            if (chat == null) return;
            var send:DisplayObject = findNamed(chat, "btnSend", 0);
            if (send == null) return;
            var target:DisplayObject = event.target as DisplayObject;
            while (target != null && target != chat) {
                if (target == send) {
                    consumeChatCommand(event, chat);
                    return;
                }
                target = target.parent;
            }
        }

        private function findNamed(node:DisplayObject, name:String, depth:int):DisplayObject {
            if (node == null || depth > 12) return null;
            if (node.name == name) return node;
            var container:DisplayObjectContainer = node as DisplayObjectContainer;
            if (container != null) {
                for (var i:int = 0; i < container.numChildren; i++) {
                    var found:DisplayObject = findNamed(container.getChildAt(i), name, depth + 1);
                    if (found != null) return found;
                }
            }
            return null;
        }

        public function getLoginControlBounds(name:String):Object {
            var control:DisplayObject = findNamed(gameLoader, name, 0);
            if (control == null) return null;
            var bounds:Rectangle = control.getBounds(this);
            var clip:MovieClip = control as MovieClip;
            var enabled:Boolean = control.visible && control.mouseEnabled;
            if (clip != null) enabled = enabled && clip.buttonMode && clip.currentLabel != "GREYOUT" && clip.hasEventListener(MouseEvent.CLICK);
            return {x:bounds.x, y:bounds.y, width:bounds.width, height:bounds.height, enabled:enabled};
        }

        private function inspectRemembered():void {
            if (cookieManager == null) return;
            var data:Object = cookieManager.getObjectData("loginInfo");
            var names:Array = [];
            for (var i:int = 0; i < 6; i++) {
                if (data["userName" + i] == null) break;
                names.push(String(data["userName" + i]).toLowerCase());
            }
            var signature:String = names.join("|");
            if (signature != rememberedNames) {
                rememberedNames = signature;
                ExternalInterface.call("onMogobeRememberedAccounts", names);
            }
        }

        private function inspectLoginView():void {
            if (currentLogin != null && loginKind == "saved" && currentLogin != laidOutLogin) {
                layoutSavedPicker();
                laidOutLogin = currentLogin;
            }
            if (currentLogin != null && currentLogin != hookedLogin) {
                hookedLogin = currentLogin;
                currentLogin.addEventListener(Event.COMPLETE, onLoginRequested, false, 100);
            }
            if (currentLogin != null && loginKind != "servers" && registrationUser != "") {
                var info:Object = Object(currentLogin).loginInfo;
                info.userName = registrationUser;
                info.password = "__MOGOBE_CURRENT_SESSION__";
                info.saveUserName = true;
                info.savePassword = false;
                info.lang = 5;
                registrationUser = "";
                // Use the original login-to-server-list flow with the existing
                // HttpOnly session. No registration password enters this SWF.
                currentLogin.dispatchEvent(new Event(Event.COMPLETE));
            }
            var selected:String = "";
            var names:Array = [];
            if (currentLogin != null) {
                var holder:DisplayObjectContainer = findNamed(currentLogin, "mcBigPreviewHolderInst", 0) as DisplayObjectContainer;
                var name:TextField;
                if (holder != null) {
                    name = findNamed(holder, "txtNameSmall", 0) as TextField;
                    if (name != null) selected = showDisplayName(name);
                }
                for (var i:int = 1; i <= 4; i++) {
                    holder = findNamed(currentLogin, "mcSmallPreviewHolderInst" + i, 0) as DisplayObjectContainer;
                    if (holder != null) {
                        name = findNamed(holder, "txtNameSmall", 0) as TextField;
                        if (name != null) {
                            var displayName:String = showDisplayName(name);
                            if (displayName != "") names.push(displayName);
                        }
                    }
                }
            }
            var signature:String = loginKind + ":" + names.join("|") + ":" + selected;
            if (signature != lastLoginView) {
                lastLoginView = signature;
                ExternalInterface.call("onMogobeLoginView", loginKind, names, selected);
            }
        }

        private function showDisplayName(source:TextField):String {
            var canonical:Object = displayNames["$" + source.text.toLowerCase()];
            var value:String = canonical == null ? source.text : String(canonical);
            var label:TextField = source.parent.getChildByName("mogobeDisplayName") as TextField;
            if (label == null) {
                label = new TextField();
                label.name = "mogobeDisplayName";
                label.mouseEnabled = false;
                label.selectable = false;
                source.parent.addChild(label);
            }
            // Original handlers compare these names case-sensitively when
            // removing saved users. Keep their internal key and render the
            // server's spelling in the same place with the original formatting.
            var format:TextFormat = source.getTextFormat();
            format.align = TextFormatAlign.CENTER;
            format.leftMargin = 0;
            format.rightMargin = 0;
            format.indent = 0;
            label.defaultTextFormat = format;
            label.embedFonts = source.embedFonts;
            label.antiAliasType = source.antiAliasType;
            label.gridFitType = source.gridFitType;
            var localBounds:Rectangle = source.getBounds(source);
            label.transform.matrix = new Matrix();
            label.width = localBounds.width;
            label.height = localBounds.height;
            var placement:Matrix = source.transform.matrix.clone();
            placement.tx += placement.a * localBounds.x + placement.c * localBounds.y;
            placement.ty += placement.b * localBounds.x + placement.d * localBounds.y;
            label.transform.matrix = placement;
            label.filters = source.filters;
            label.text = value;
            label.setTextFormat(format);
            label.visible = source.visible && value != "";
            source.alpha = 0;
            return value;
        }

        private function layoutSavedPicker():void {
            var holders:Array = [];
            var positions:Array = [];
            for (var i:int = 1; i <= 4; i++) {
                var holder:DisplayObject = findNamed(currentLogin, "mcSmallPreviewHolderInst" + i, 0);
                if (holder == null) return;
                holders.push(holder);
                positions.push(holder.x);
            }
            // Keep the original data/index mapping and move whole holders into
            // left-to-right order. Text and avatars retain their original scale.
            positions.sort(Array.NUMERIC);
            for (i = 0; i < holders.length; i++) holders[i].x = positions[i];
            var previous:DisplayObject = findNamed(currentLogin, "btnLeftI", 0);
            var next:DisplayObject = findNamed(currentLogin, "btnRightI", 0);
            if (previous == null || next == null) return;
            var previousBounds:Rectangle = previous.getBounds(previous.parent);
            var nextBounds:Rectangle = next.getBounds(next.parent);
            var previousCenter:Number = previousBounds.x + previousBounds.width / 2;
            var nextCenter:Number = nextBounds.x + nextBounds.width / 2;
            if (previousCenter > nextCenter) {
                previous.scaleX = -previous.scaleX;
                next.scaleX = -next.scaleX;
                previousBounds = previous.getBounds(previous.parent);
                nextBounds = next.getBounds(next.parent);
                previous.x += nextCenter - previousBounds.x - previousBounds.width / 2;
                next.x += previousCenter - nextBounds.x - nextBounds.width / 2;
            }
        }

        private function findMain(node:DisplayObject, depth:int):void {
            if ((node != gameLoader && !node.visible) || depth > 8) return;
            var type:String = getQualifiedClassName(node);
            if (type == "Main") {
                mainClip = node as DisplayObjectContainer;
                return;
            }
            if (type == "mogobe.login::LoginScreen" || type == "mogobe.serversList::ServersList") {
                hasLobby = true;
                if (type == "mogobe.login::LoginScreen") {
                    currentLogin = node as DisplayObjectContainer;
                    loginKind = "single";
                    for (var k:int = 0; k < currentLogin.numChildren; k++) {
                        if (getQualifiedClassName(currentLogin.getChildAt(k)) == "mogobe.login::LoginScreenMulti") loginKind = "saved";
                    }
                } else {
                    loginKind = "servers";
                    if (node != hookedServers) {
                        hookedServers = node as DisplayObjectContainer;
                        hookedServers.addEventListener(Event.SELECT, onWorldSelected, false, 100);
                    }
                }
                return;
            }
            var container:DisplayObjectContainer = node as DisplayObjectContainer;
            if (container != null) {
                for (var i:int = 0; i < container.numChildren; i++) {
                    findMain(container.getChildAt(i), depth + 1);
                    if (mainClip != null) return;
                }
            }
        }

        private function inspectScene(event:Event):void {
            hasLobby = false;
            mainClip = null;
            currentLogin = null;
            loginKind = "";
            findMain(gameLoader, 0);
            updateServerPresence();
            inspectLoginView();
            inspectRemembered();
            var state:String = "loading";
            var room:String = "";
            var panelReady:Boolean = false;
            var avatarReady:Boolean = false;
            worldAvatar = null;
            if (mainClip != null) {
                for (var i:int = 0; i < mainClip.numChildren; i++) {
                    var child:DisplayObject = mainClip.getChildAt(i);
                    if (!child.visible) continue;
                    var type:String = getQualifiedClassName(child);
                    if (type == "mlControlPanel") {
                        var buttons:DisplayObject = (child as DisplayObjectContainer).getChildByName("mcControlButtons");
                        panelReady = buttons != null && buttons.visible;
                    }
                    var roomView:DisplayObjectContainer = child as DisplayObjectContainer;
                    var zOrder:DisplayObjectContainer = roomView == null ? null : roomView.getChildByName("mcZOrder") as DisplayObjectContainer;
                    if (type.indexOf("ml") == 0 && zOrder != null && roomView.getChildByName("mcWalkingArea") != null) {
                        prepareRoomView(roomView);
                        room = type.substr(2).toLowerCase();
                        if (zOrder != null) {
                            for (var j:int = 0; j < zOrder.numChildren; j++) {
                                var avatar:DisplayObject = zOrder.getChildAt(j);
                                if (getQualifiedClassName(avatar) == "worlds4u.view.avatar::MyAvatar" && avatar.visible) {
                                    avatarReady = true;
                                    worldAvatar = avatar;
                                    break;
                                }
                            }
                        }
                    }
                }
                if (room != "" && panelReady && avatarReady) state = "world";
            } else if (hasLobby && !worldStarting) {
                state = "lobby";
            }
            refreshFriendsFonts();
            updateFriendTooltip();
            updateProfileCounters();
            if (loginKind == "servers") registrationPending = false;
            if (registrationPending) state = "loading";
            // Suppress input while original Main is building the room/panel.
            gameLoader.mouseChildren = state != "loading";
            gameLoader.mouseEnabled = state != "loading";
            var signature:String = state + ":" + room;
            if (signature != lastState) {
                lastState = signature;
                showOriginalLoading(state == "loading");
                ExternalInterface.call("onMogobeSceneState", state, room, panelReady, avatarReady);
            }
        }
        private var shopPopup:Object;
        private var shopModel:flash.events.EventDispatcher;
        private var shopData:Object;

        public function openOriginalShop(data:Object):Boolean {
            if (mainClip == null || worldAvatar == null) return false;
            var existing:Object = currentPopup();
            if (existing != null && existing != shopPopup) return false;
            if (shopPopup != null && shopPopup.baseView.stage != null) {
                if (shopData.key == data.key && shopData.kind == data.kind) {
                    refreshOriginalShop(data);
                    return true;
                }
                closeOriginalShop();
            }
            shopData = data;
            shopModel = new flash.events.EventDispatcher();
            var cls:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.view.popups.PopupsManeger") as Class;
            shopPopup = Object(cls).getInstance().showPopWithLoad(33,{popupId:data.kind == "clothing" ? 2 : 6},shopModel);
            shopPopup.addEventListener("STORE_DATA_EVT",shopRequest);
            shopPopup.addEventListener("ASK_DATA_EVT",shopRequest);
            shopPopup.addEventListener("BUY_ITEM_EVT",shopRequest);
            shopPopup.addEventListener(Event.CLOSE,shopClosed);
            return true;
        }

        private function shopClosed(event:Event):void {
            shopPopup = null;
            shopModel = null;
            shopData = null;
            ExternalInterface.call("onMogobeShopClosed");
        }

        private function shopRequest(event:Event):void {
            if (shopData == null) return;
            var cls:Class;
            if (event.type == "STORE_DATA_EVT") {
                var store:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.model.data.StoreTO") as Class;
                cls = ApplicationDomain.currentDomain.getDefinition("worlds4u.events.RoomEvent") as Class;
                shopModel.dispatchEvent(new cls("STORE_DATA_EVT",new store(shopData),"rooms__getStoreData"));
            } else if (event.type == "ASK_DATA_EVT") {
                sendShopUser();
            } else if (event.type == "BUY_ITEM_EVT") {
                var id:int = int(Object(event).Data);
                var price:int = -1;
                for each (var item:Object in shopData.items) if (int(item.typeId) == id) price = int(item.price);
                ExternalInterface.call("onMogobeShopBuy",shopData.key,id,price);
            }
        }

        private function sendShopUser():void {
            if (shopData == null || shopModel == null) return;
            var userClass:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.model.data.UserTO") as Class;
            var user:Object = new userClass(int(shopData.user.userId),String(shopData.user.userName),true);
            var values:Array = [];
            for (var key:String in shopData.user) values[key] = shopData.user[key];
            values["mo_1"] = shopData.coins;
            user.Varibales = values;
            var cls:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.events.AvatarEvent") as Class;
            shopModel.dispatchEvent(new cls("ASK_DATA_EVT","user__getUserTO",user,int(shopData.user.userId)));
        }

        public function refreshOriginalShop(data:Object):void {
            if (shopPopup == null || shopData == null || data.key != shopData.key) return;
            shopData = data;
            var store:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.model.data.StoreTO") as Class;
            var cls:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.events.RoomEvent") as Class;
            shopModel.dispatchEvent(new cls("STORE_DATA_EVT",new store(data),"rooms__getStoreData"));
            sendShopUser();
        }

        public function finishShopPurchase(success:Boolean):void {
            if (shopModel == null) return;
            var cls:Class = ApplicationDomain.currentDomain.getDefinition("worlds4u.events.AvatarEvent") as Class;
            shopModel.dispatchEvent(new cls("BUY_ITEM_EVT","user__buyItem",{status:success,msgId:-1},-1));
        }

        public function closeOriginalShop():void {
            if (shopPopup == null) return;
            try { shopPopup.disableEvents(); } catch (error:Error) {}
            shopPopup.dispatchEvent(new Event(Event.CLOSE));
        }

        private function countShopGraphics(node:DisplayObject):int {
            var type:String = getQualifiedClassName(node);
            var result:int = type.indexOf("btnItem") == 0 || type.indexOf("mlBigItem") == 0 ? 1 : 0;
            var holder:DisplayObjectContainer = node as DisplayObjectContainer;
            if (holder != null) for (var i:int = 0; i < holder.numChildren; i++) result += countShopGraphics(holder.getChildAt(i));
            return result;
        }

        private function findShopGraphic(node:DisplayObject, prefix:String):DisplayObject {
            if (getQualifiedClassName(node).indexOf(prefix) == 0) return node;
            var holder:DisplayObjectContainer = node as DisplayObjectContainer;
            if (holder != null) for (var i:int = 0; i < holder.numChildren; i++) {
                var found:DisplayObject = findShopGraphic(holder.getChildAt(i),prefix);
                if (found != null) return found;
            }
            return null;
        }

        private function shopCells(node:DisplayObject, result:Array):void {
            if (getQualifiedClassName(node) == "worlds4u.common.uiControls.DataGrid::GridCellStore") {
                var data:Object = Object(node).Data;
                var bounds:Rectangle = node.getBounds(this);
                var hit:flash.geom.Point = globalToLocal(node.localToGlobal(new flash.geom.Point(42.85,31.95)));
                var artwork:DisplayObject = findShopGraphic(node,"btnItem");
                var artBounds:Rectangle = artwork == null ? null : artwork.getBounds(node);
                result.push({art:artBounds == null ? null : {x:artBounds.x,y:artBounds.y,width:artBounds.width,height:artBounds.height},hitX:hit.x,hitY:hit.y,id:int(data.TypeId),price:int(data.Price),available:Boolean(data.InStock),
                    x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height,
                    graphics:countShopGraphics(node)});
            }
            var holder:DisplayObjectContainer = node as DisplayObjectContainer;
            if (holder != null) for (var i:int = 0; i < holder.numChildren; i++) shopCells(holder.getChildAt(i),result);
        }

        public function getShopInfo():Object {
            if (shopPopup == null || shopData == null) return null;
            var cells:Array = [];
            shopCells(shopPopup.baseView,cells);
            var preview:DisplayObject = findNamed(shopPopup.baseView,"mcAvatarBig",0);
            var panel:DisplayObjectContainer = findNamed(shopPopup.baseView,"mcShop",0) as DisplayObjectContainer;
            var luxury:DisplayObject = panel == null ? null : panel.getChildByName("txtAmount_2");
            var amount:DisplayObject = panel == null ? null : panel.getChildByName("txtAmount_1");
            return {luxuryVisible:luxury != null && luxury.visible,coinY:amount == null ? 0 : amount.y,
                key:shopData.key,title:shopData.title,kind:shopData.kind,coins:shopData.coins,
                itemCount:shopData.items.length,items:cells,text:collectText(shopPopup.baseView),
                visible:shopPopup.baseView.stage != null,avatar:preview != null && preview.visible};
        }


    }
}
