/* -----------      cookies        --------------------*/
function createCookie(c_name,value,expiredays)
{
    var exdate=new Date();
    exdate.setDate(exdate.getDate()+expiredays);
    document.cookie=c_name+ "=" +escape(value)+
    ((expiredays==null) ? "" : ";expires="+exdate.toGMTString());
}

function readCookie(name) {
	var nameEQ = name + "=";
	var ca = document.cookie.split(';');
	for(var i=0;i < ca.length;i++) {
		var c = ca[i];
		while (c.charAt(0)==' ') c = c.substring(1,c.length);
		if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
	}
	return null;
}

function eraseCookie(name) {
	createCookie(name,"",-1);
}


function doOverEffect(oEvent)
{
    var obj = getObjectFromEvent(oEvent);
    obj.src = obj.src.replace(".gif","_over.gif")
     obj.src = obj.src.replace("_down.gif","_over.gif")
}
    
function getObjectFromEvent(oEvent)
{
    return (oEvent.target || oEvent.srcElement);
}
    
function doOutEffect(oEvent)
{
    var obj = getObjectFromEvent(oEvent);
    obj.src = obj.src.replace("_over.gif",".gif");
    obj.src = obj.src.replace("_down.gif",".gif")
}

function openRegistWindow()
{
    url = "/Registration1.aspx";
    name = "_blank";
    
    var vars =  "toolbar=no, ";
        vars += "location=no, ";
        vars += "toolbar=no, ";
        vars += "directories=no, ";
        vars += "status=no, ";
        vars += "menubar=no, ";
        vars += "resizable=yes, ";
        vars += "scrollbars=auto, ";
        vars += "width=980, ";
        vars += "height=690, ";
        vars += "left=0, ";
        vars += "top=0";
    
    window.open(url, name, vars);

}

///--- languge 
function setLanguage(lang)
{   
    createCookie("lang",lang,365);
}

function setLangAndReload(lang)
{
    setLanguage(lang);
    
    window.location.reload();
}


function validateEmail(str) {

		var at="@"
		var dot="."
		var lat=str.indexOf(at)
		var lstr=str.length
		var ldot=str.indexOf(dot)
		if (str.indexOf(at)==-1){
		   //alert("Invalid E-mail ID")
		   return false
		}

		if (str.indexOf(at)==-1 || str.indexOf(at)==0 || str.indexOf(at)==lstr){
		   //alert("Invalid E-mail ID")
		   return false
		}

		if (str.indexOf(dot)==-1 || str.indexOf(dot)==0 || str.indexOf(dot)==lstr){
		    //alert("Invalid E-mail ID")
		    return false
		}

		 if (str.indexOf(at,(lat+1))!=-1){
		    alert("Invalid E-mail ID")
		    return false
		 }

		 if (str.substring(lat-1,lat)==dot || str.substring(lat+1,lat+2)==dot){
		    //alert("Invalid E-mail ID")
		    return false
		 }

		 if (str.indexOf(dot,(lat+2))==-1){
		    ///alert("Invalid E-mail ID")
		    return false
		 }
		
		 if (str.indexOf(" ")!=-1){
		    //alert("Invalid E-mail ID")
		    return false
		 }

 		 return true					
	}
	
function querySt(ji) 
{
    hu = window.location.search.substring(1);
    gy = hu.split("&");
    for (i=0;i<gy.length;i++)
    {
        ft = gy[i].split("=");
        if (ft[0] == ji)
        {
            return ft[1];
        }
    }
}


Array.prototype.shift = function(str)
{
  var val = this[0];
  for (var i = 1; i < this.length; ++i) {
    this[i-1] = this[i];
  }
  this.length--;
  return val;
}
