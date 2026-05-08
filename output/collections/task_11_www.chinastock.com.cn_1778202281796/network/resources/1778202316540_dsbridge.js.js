function getJsBridge() {
  window._dsf = window._dsf || {};
  return {
    call: function (method, args, cb) {
      var ret = "";
      if (typeof args == "function") {
        cb = args;
        args = {};
      }
      if (typeof cb == "function") {
        window.dscb = window.dscb || 0;
        var cbName = "dscb" + window.dscb++;
        window[cbName] = cb;
        args["_dscbstub"] = cbName;
      }
      args = JSON.stringify(args || {});
      try {
        if (window._dswk) {
          ret = prompt(window._dswk + method, args);
        } else {
          if (typeof _dsbridge == "function") {
            ret = _dsbridge(method, args);
          } else {
            ret = _dsbridge.call(method, args);
          }
        }
      } catch (error) {
        //console.log(error);
        if (error instanceof ReferenceError) {
          //console.log("发生了 ReferenceError");//ios低版本有ua，没有注入jsbridge，跳提示更新页
          var oldapp = getHtml();
         // console.log(oldapp);
          document.getElementById("app").innerHTML = oldapp;
        } else {
          //console.log("发生了其他类型的错误");
        }
      } finally {
       
      }
      return ret;
    },
    register: function (name, fun) {
      if (typeof name == "object") {
        Object.assign(window._dsf, name);
      } else {
        window._dsf[name] = fun;
      }
    },
  };
}
window.dsBridge = getJsBridge();
