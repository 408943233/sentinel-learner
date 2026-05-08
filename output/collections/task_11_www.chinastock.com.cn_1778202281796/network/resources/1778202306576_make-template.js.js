/**
 * 版本日期 2023-06-09
 **/
;function makeTemplate(){
	var data={},tagName;
	var inner={
		/*生成节点HTML*/
		setHtml:function(){
			if(!this.getTag()) return;
			var html=this.simple(this.getTagHtml());
			var render=this.replaceTemplate(html);
			var auto= new Array();
			var c = $(this.getTag()).find('.__scroll_auto__');
			if(c.length > 0){
				for(var i = 0; i < c.length;i++) auto[i]=c.eq(i).scrollTop();
			}
			this.getTag().innerHTML = render(data);
			if(auto.length > 0) {
				for(var i = 0; i < auto.length;i++) {
					$(this.getTag()).find('.__scroll_auto__').eq(i).animate({
						scrollTop: auto[i]
					},0);
				}
			}
		},
		/*获取原始HTML*/
		getTagHtml:function(){
			if(data['tagHtml_'+tagName]) return data['tagHtml_'+tagName];
			if(this.getTag() == null) return;
			var html=this.getTag().innerHTML;
			var tagHtml=this.revertHtml(html);
			data['tagHtml_'+tagName]=tagHtml;
			return tagHtml;
		},
		/*获取节点*/
		getTag:function(){
			if(data['tag_'+tagName]) return data['tag_'+tagName];
			if(tagName.substr(0, 1) == '#'){
				var tag=document.getElementById(tagName.slice(1));
			}else if(tagName.substr(0, 1) == '.'){
				var tag=document.getElementsByClassName(tagName.slice(1));
				tag = tag[0];
			}else{
				var tag=document.getElementsByTagName(tagName);
				tag = tag[0];
			}
			data['tag_'+tagName]=tag;
			return tag;
		},
		/*还原HTML 字符*/
		revertHtml:function(str){
			return str.replace(/$#39;|&lt;|&gt;|&quot;|&amp;/g,function(match){
				switch (match) {case '&lt;':return '<';case '&gt;':return '>';case '&quot;':return '"';case '&amp;':return '&';case "$#39;":return '\\';}
			});
		},
		/*编译替换HTML*/
		replaceTemplate:function(str){
			if(!str) return;
			var interpolate=/<%=(.+?)%>/g,evaluate=/<%(.+?)%>/g;
			var matcher = new RegExp(interpolate.source+'|'+evaluate.source+'|$',   'g'  );
			var index = 0,p = '';
			var escapes = {'\n': 'n','\r': 'r','\u2028': 'u2028','\u2029': 'u2029','\\': '\\',"'": "'"};
			var escapeReg = /[\n\r\u2028\u2029\\']/g;
			var escapeChar=function(match){return '\\' + escapes[match]};
			str.replace(matcher, function (match, interpolate, evaluate, offset) {
				p += str.slice(index, offset).replace(escapeReg, escapeChar);
				index = offset + match.length;
				if (interpolate) {
					p += "' + ("+interpolate+") + '";
				} else if (evaluate) {
					p += "'; "+evaluate+" p+='";
				}
				return match;
			})
			p = "var p = ''; with(data){ p+='" + p + "';} return p;";
			//console.log(p);
			try {
				return new Function('data', p);
			} catch (e) {
				console.log(e);
			}
		},
		/*替换标签*/
		simple:function(str){
			if(!str) return;

			/*预处理标签 attr-if*/
			var attrif=/attr\-if\=\"(.*?)\{\{\/if\}\}\"/ig;
			var result = str.match(attrif);
			//console.log(str);
			if(result){
				for(var i in result){
					var tempAttr=result[i].substring(0,result[i].length-1);
					tempAttr=tempAttr.replace("attr-if=\"",'');
					str=str.replace(result[i],tempAttr);
				}
			}

			/*处理for*/
			var forexp=/\{\{for(.+?)\}\}/ig;
			var result = str.match(forexp);
			if(result){
				for(var i in result){
					var exp=/\(.+?\)/;
					var temp=result[i].toString().match(exp);
					if(temp){
						var repString="<\% for "+temp[0]+" { \%>";
						str=str.replace(result[i],repString);
					}
				}
			}
			var forend=/\{\{\/for\}\}/ig;
			var result = str.match(forend);
			if(result){
				for(var i in result){
					var repString="<\% } \%>";
					str=str.replace(result[i],repString);
				}
			}
			/*处理if */
			str=str.replace(/<\/elseif>/ig,'');
			str=str.replace(/<\/else>/ig,'');
			var ifexp=/\{\{if(.*?)\}\}/ig;
			var result = str.match(ifexp);
			if(result){
				for(var i in result){
					var exp=/\(.+?\)/;
					var temp=result[i].toString().match(exp);
					if(temp){
						var repString="<\% if "+temp[0]+" { \%>";
						str=str.replace(result[i],repString);
					}
				}
			}
			var elseIf=/\{\{elseif(.*?)\}\}/ig;
			var result = str.match(elseIf);
			if(result){
				for(var i in result){
					var exp=/\(.+?\)/;
					var temp=result[i].toString().match(exp);
					if(temp){
						var repString="<\% } else if  "+temp[0]+" { \%>";
						str=str.toString().replace(result[i],repString);
					}
				}
			}
			var elses=/\{\{else\}\}/ig;
			var result = str.match(elses);
			if(result){
				for(var i in result){
					var repString="<\% } else { \%>";
					str=str.toString().replace(result[i],repString);
				}
			}
			var ifend=/\{\{\/if\}\}/ig;
			var result = str.match(ifend);
			if(result){
				for(var i in result){
					var repString="<\% } \%>";
					str=str.toString().replace(result[i],repString);
				}
			}
			/*变量*/
			var vars=/\{\{(.+?)\}\}/ig;
			var result = str.match(vars);
			if(result){
				for(var i in result){
					temp=result[i].toString().replace("{{",'');
					temp=temp.replace("}}",'');
					var repString="<\%="+(temp)+"\%>";
					str=str.toString().replace(result[i],repString);
				}
			}
			/*替换 -block-tag */
			var reg=/\-block\-tag/g;
			str=str.replace(reg,'');
			return str;
		}
	};
	var exterior={
		/*设置data值*/
		setData:function(object,isInit){
			isInit = arguments[1] ? arguments[1] : false;
			for(var i in object) data[i]=object[i];
			if(isInit) return;
			inner.setHtml();
			return exterior;
		},
		/*获取data值*/
		getData:function(){
			return data;
		},
		/*解决innerHTML 后所有事件失效，除了使用回调方法未找到其它解决办法*/
		htmlCallback:function(method){
			if(!method) return;
			typeof(method) == 'function' && method();
			typeof(method) == 'string' && eval(method)();
		},
		/*接授节点*/
		node:function(nodeId){
			tagName=nodeId;
			return exterior;
		},
		/*无限级递归子分类*/
		recurrence:function(object,pidString,idString,childString,pid){
			var array=[];
			var j=0;
			for(var i in object){
				if(object[i][pidString]==pid){
					object[i][childString]=exterior.recurrence(object,pidString,idString,childString,object[i][idString]);
					array[j++]=object[i];
				}
			}
			return array;
		},
		/*转码URL*/
		urlencode:function(str){
			str = (str + '').toString();
			return encodeURIComponent(str).replace(/!/g, '%21').replace(/'/g, '%27').replace(/\(/g, '%28').
			replace(/\)/g, '%29').replace(/\*/g, '%2A').replace(/%20/g, '+');
		},
		/*获取GET参数*/
		getQueryString:function(name){
			var reg = new RegExp("(^|&)" + name + "=([^&]*)(&|$)");
			var r =  decodeURI(window.location.search.substr(1)).match(reg);
			if (r != null) {
				return r[2] ? unescape(r[2]) : '';
			}
			return '';
		},
		/*正则表达式实现html编码（转义）*/
		htmlToEscape:function(s){
			if(!s) return '';
			return s.replace(/[<>&"']/g,function(c){return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":"&apos;"}[c];});
		},
		/*用正则表达式实现html解码（反转义）*/
		escapeToHtml:function(s){
			if(!s) return '';
			var arrEntities={'lt':'<','gt':'>','nbsp':' ','amp':'&','quot':'"',"apos":"'"};
			return s.replace(/&(lt|gt|nbsp|amp|quot|apos);/ig,function(all,t){return arrEntities[t];});
		},
		/*写入cookie*/
		setCookie:function(name, value) {
			var Days = 30;
			var exp = new Date();
			exp.setTime(exp.getTime() + Days * 24 * 60 * 60 * 1000);
			document.cookie = name + "=" + escape(value) ;
		},
		/*读取cookie*/
		getCookie:function(name) {
			var arr, reg = new RegExp("(^| )" + name + "=([^;]*)(;|$)");
			if(arr = document.cookie.match(reg))
				return unescape(arr[2]);
			else
				return '';
		}
	}
	return exterior;
};
//调用业务=================================================
window.make = makeTemplate();
//登录后返回URI
var loginRturnUrl=make.urlencode((window.location.pathname+window.location.search).slice(1));
//职位类型
var Category=make.htmlToEscape(make.getQueryString('Category'));
//招聘单位GET参数
var ClassificationTwo=make.htmlToEscape(make.getQueryString('ClassificationTwo'));
//职位分类GET参数
var ClassificationOne=make.htmlToEscape(make.getQueryString('ClassificationOne'));
//职位分类3GET参数
var Classification3=make.htmlToEscape(make.getQueryString('Classification3'));

//区域GET参数
var LocId=make.htmlToEscape(make.getQueryString('LocId'));
//关键字GET参数
var KeyWords=make.htmlToEscape(make.getQueryString('KeyWords'));
//发布时间
var PostDate=make.htmlToEscape(make.getQueryString('PostDate'));
//活动ID
var activityGuid=make.htmlToEscape(make.getQueryString('activityGuid'));
//初始化数据
make.setData({
	//职位详情页数据
	result:{},
	//职位分类
	positionCategory:[],
	// 机构类型
	Classification3: [],
	//招聘部门
	department:[],
	//工作地点
	workPlace:[],
	//职位列表
	list:[],
	//热招职位列表【通常是详情页使用】
	hotJobAdList:[],
	//是否登录
	isLogin:false,
	//登录后返回URI
	loginURL:loginRturnUrl,
	//用户昵称
	UserName:'',
	//无数据时显示
	notData:false,
	//显示加载状态
	isLoad:false,
	//进条度比例
	ratioNumber:0,
	//进条度ID
	ratiorunId:0,
	//加载完成状态
	loadComplete:false,
	//显示首次进入面页
	isFirstLoad:false,
	//分页是否追加数据
	isPageAppend:false,
	//检索参数
	query:{
		//职位类型(1：社招 2：校招 3：实习生招聘,4海外校招，5海外社招，6技术校招，7培优校招)
		//传参数组形式 ["1"]
		Category:Category ? [Category] : [],
		//活动ID
		ActivityGuid:activityGuid ? activityGuid : "",
		//工作地点
		LocId:LocId,
		//分类1[职位分类]
		ClassificationOne:ClassificationOne,
		//分类2[招聘部门]
		ClassificationTwo:ClassificationTwo,
		//分类3
		Classification3:Classification3,
		//分类4
		Classification4:"",
		//分类5
		Classification5:"",
		//分类6
		Classification6:"",
		//发布时间
		PostDate:PostDate,
		//关键字检索
		KeyWords:KeyWords,
		//热招职位：1 长招职位：2
		SpecialType:0,
		//PortalId ID
		PortalId:"",
		//页码
		PageIndex:"0",
		//分页大小
		PageSize:"20",
		//获取字段
		DisplayFields:['Category','Kind','LocId','Org','HeadCount','Station','EndTime','PostDate','ClassificationOne','ClassificationTwo', 'Classification3']
	},
	//当前页码
	PrevPage:0,
	//展示分页数据
	pages:{
		prev:-1,
		left_ellipsis:"",
		list:[],
		right_ellipsis:"",
		next:0
	},
	//微信分享图片
	allShareImg:'https://yuege-beijing.oss-cn-beijing.aliyuncs.com/chinastock/phimg/sharelogo.jpg',
	//其它扩展模板变量，可以在外部实现付值
	extend:{}
},true);

/*页面上拉触底事件*/
make.onReachBottom=function(_function){
	$(window).scroll(function() {
		if(make.getData().loadComplete || make.getData().isLoad || make.getData().notData) return;//加载完成状态
		var h = $("body").height() ;
		var scrolled = $(window).scrollTop() / (h - $(window).height());
		if(scrolled >= 0.92){ //触发底线可调一般 百分之92触发
			make.getData().query.PageIndex=parseInt(make.getData().query.PageIndex)+1;
			typeof(_function) == 'function' && _function();
		}
	});
};
/**转换日期*/
make.timestampToTime=function(timestamp) {
	timestamp = timestamp/1000;
	var date = new Date(timestamp * 1000);
	var Y = date.getFullYear() + '-';
	var M = (date.getMonth()+1 < 10 ? '0'+(date.getMonth()+1) : date.getMonth()+1) + '-';
	var D = (date.getDate() < 10 ? '0'+date.getDate() : date.getDate()) + ' ';
	return Y+M+D;
};
//传入日期//例：2020-10-27T14:36:23
make.timeFormatSeconds = function(time) {
	var d = time ? new Date(time) : new Date();
	var year = d.getFullYear();
	var month = d.getMonth() + 1;
	var day = d.getDate();
	var hours = d.getHours();
	var min = d.getMinutes();
	var seconds = d.getSeconds();
	if (month < 10) month = '0' + month;
	if (day < 10) day = '0' + day;
	if (hours < 10) hours = '0' + hours;
	if (min < 10) min = '0' + min;
	if (seconds < 10) seconds = '0' + seconds;
	//return (year + '-' + month + '-' + day + ' ' + hours + ':' + min + ':' + seconds);
	return (year + '-' + month + '-' + day );
}

/**生成进条度*/
make.setLoads=function(){
	var that=make;
	make.getData().isLoad=true;
	if($('#__mobileLoad__').length > 0) {
		make.node('#__mobileLoad__').setData({});
		$('#__mobileLoad__').show();
	}
	var i=1;
	make.getData().ratiorunId=setInterval(function(){
		if(!(i >=30 && i <=60)) {
			that.node('#__advance__').setData({ratioNumber:i});
		}
		i++;
		if(i>=92) {
			clearInterval(make.getData().ratiorunId);
			that.node('#__advance__').setData({ratioNumber:92});
		}
	},20);
};
//关闭进条度
make.closeLoads=function(){
	var that=make;
	clearInterval(make.getData().ratiorunId);
	that.node('#__advance__').setData({ratioNumber:100});
	setTimeout(function(){
		make.getData().isLoad=false;
		if($('#__mobileLoad__').length > 0) {
			make.node('#__mobileLoad__').setData({});
			$('#__mobileLoad__').show();
		}
		that.node('#__advance__').setData({ratioNumber:0});
	},200);
};

/*定位到头部职位*/
make.goMarginTop=function(){
	var id='#__fixed_position__';
	if($(id).length > 0){
		$('body,html').animate({
			scrollTop:$(id).offset().top
		}, 1000);
	}
};

/*生成分页*/
make.setPage=function(Count){
	var PageIndex=parseInt(make.getData().query.PageIndex);
	var pages={};
	var totalPage= Math.ceil(Count/parseInt(make.getData().query.PageSize));
	if(totalPage <= 0){
		make.getData().pages.prev=-1;
		make.getData().pages.next=0;
		make.getData().pages.list=[];
		pages.page=PageIndex+1;
		pages.totalPage=totalPage > 0 ? totalPage-1 : 0;
		make.getData().pages.left_ellipsis="";
		make.getData().pages.right_ellipsis="";
		if($('#__JobAdList_page__').length){
			make.node('#__JobAdList_page__').setData({});
			$('#__JobAdList_page__').show();
		}
		return;
	}
	if(PageIndex >= totalPage-1) PageIndex=totalPage-1;
	pages.first_page=-1;
	pages.last_page=-1;
	pages.next=0;
	pages.prev=-1;
	pages.next=0;
	pages.PageIndex=PageIndex;
	pages.totalPage=totalPage > 0 ? totalPage-1 : 0;
	pages.list=[];
	pages.left_ellipsis="";
	pages.right_ellipsis="";
	if(totalPage <= 0) return pages;
	if(PageIndex == 0) pages.prev=-1;
	else if((PageIndex - 1) >= 0) pages.prev=PageIndex - 1;
	if(PageIndex+1 < totalPage-1) pages.next=PageIndex+1;
	else if(PageIndex+1 > totalPage-1) pages.next=-1;
	else pages.next=PageIndex+1;
	var t=0;
	/* 生成页数 */
	if (totalPage <= 10) {
		// 总页数小于等于10页全部显示
		for (var i = 0; i < totalPage; i++) {
			var temp={};
			temp.now=false;
			temp.number=i;
			if(i == PageIndex) temp.now=true;
			pages.list[t++]=temp;
		}
	} else if (PageIndex < 7) {
		//总页数大于10且当前页远离总页数
		for (var i = 0; i <= 8; i++) {
			var temp={};
			temp.now=false;
			temp.number=i;
			if(i == PageIndex) temp.now=true;
			pages.list[t++]=temp;
		}
		pages.right_ellipsis="...";
	} else if (PageIndex > totalPage - 7) {
		//总页数大于10且当前页接近总页数
		for (var i = totalPage - 8; i < totalPage; i++) {
			var temp={};
			temp.now=false;
			temp.number=i;
			if(i == PageIndex) temp.now=true;
			pages.list[t++]=temp;
		}
		pages.left_ellipsis="...";
	} else {
		pages.left_ellipsis="...";
		//除开上面两个情况 当前页在中间
		for (var i = PageIndex - 3; i < PageIndex + 4; i++) {
			var temp={};
			temp.now=false;
			temp.number=i;
			if(i == PageIndex) temp.now=true;
			pages.list[t++]=temp;
		}
		pages.right_ellipsis="...";
	}
	if(pages.left_ellipsis) pages.first_page=0;
	if(pages.right_ellipsis) pages.last_page=totalPage-1;

	if($('#__JobAdList_page__').length){
		make.node('#__JobAdList_page__').setData({pages:pages});
		$('#__JobAdList_page__').show();
	}
};
//登录方法
make.login=function(node,callBack){
	make.request('/api/Login/GetUserInfo','get','',function(result){
		var isLogin=false;
		if(result.Code == 200 && result.Data.Mobile != '') isLogin=true;
		make.node(node).setData({isLogin:isLogin});
		$(node).show();
		if(typeof(callBack) == 'function') callBack(result);
	});
};
//退出方法
make.logOut=function(){
	var that=make;
	that.request('/api/Account/CancelLogin','get','',function(result){
		if(result.Code == 200){
			location.href = '/login?goto='+make.getData().loginURL;
		}
	});
};
//网络请求[异步]
make.request=function(uri,method,data,fun,errBack){
	errBack = arguments[4] ? arguments[4] : null;
	method=method.toUpperCase();
	if(data && method == 'POST') data=JSON.stringify(data);
	$.ajax({
		url:uri,
		type:method,
		contentType:'application/json; charset=utf-8',
		dataType:'json',
		data:data,
		success:function(result){
			typeof fun == "function" && fun(result);
		},
		error:function(xhr,errorText,errorType){
			console.error('错误代码：' + xhr.status + ' : ' + xhr.statusText);
			typeof errBack == "function" && errBack(xhr);
		},
		complete:function(res){

		}
	})
};
//网络请求[同步]
make.requestAsync=function(uri,method,data,fun,errBack){
	errBack = arguments[4] ? arguments[4] : null;
	method=method.toUpperCase();
	if(data && method == 'POST') data=JSON.stringify(data);
	$.ajax({
		url:uri,
		type:method,
		contentType:'application/json; charset=utf-8',
		dataType:'json',
		async:false,
		data:data,
		success:function(result){
			typeof fun == "function" && fun(result);
		},
		error:function(xhr,errorText,errorType){
			console.error('错误代码：' + xhr.status + ' : ' + xhr.statusText);
			typeof errBack == "function" && errBack(xhr);
		},
		complete:function(res){

		}
	})
};
//处理城市区域(已废弃)
make.setAreas=function(workPlace=null){
	/*var workPlace=[
         {"Text":"全国","Value":1,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":0,"Level":0,"Children":null,"Id":"00000000-0000-0000-0000-000000000000"},
         {"Text":"山东省","Value":3700,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":14,"Level":1,"Children":null,"Id":"697e4cf6-b1c0-4efe-91a9-a47163dd505b"},
         {"Text":"浙江省","Value":3300,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":13,"Level":1,"Children":null,"Id":"4629f73b-36e8-423e-ae12-5cd45aab0866"},
         {"Text":"江苏省","Value":3200,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":7,"Level":1,"Children":null,"Id":"378081f3-a7f8-44bc-abec-9cbc67798f1d"},
         {"Text":"新疆维吾尔自治区","Value":6500,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":5,"Level":1,"Children":null,"Id":"c3ddef08-8f01-49a0-ade6-4e8b0cb890d5"},
         {"Text":"河北省","Value":1300,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":2,"Level":1,"Children":null,"Id":"8efd71ef-8cce-4684-96bc-492edb18daac"},
         {"Text":"上海市","Value":3100,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":2,"Level":1,"Children":null,"Id":"086dda76-a2cb-4814-9967-38c208bffe2e"},
         {"Text":"陕西省","Value":6100,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":2,"Level":1,"Children":null,"Id":"757e14f8-9148-4840-8aae-39cb0b6f606e"},
         {"Text":"山西省","Value":1400,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":1,"Children":null,"Id":"78cb5b79-f78d-4d58-a0e2-c7dc2b8a4803"},
         {"Text":"福建省","Value":3500,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":1,"Children":null,"Id":"b1b187eb-0af9-41c6-a5d4-74b9a79095cd"},
         {"Text":"江西省","Value":3600,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":1,"Children":null,"Id":"5609fcfa-aa08-4a58-bde1-9ba97fbcd9bd"},
         {"Text":"重庆市","Value":5000,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":1,"Children":null,"Id":"56595510-3115-4c50-8d36-a6ee966495bf"},
         {"Text":"武汉市","Value":4201,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":17,"Level":2,"Children":null,"Id":"8593824e-f775-4327-9079-c9cce86aae43"},
         {"Text":"滨州市","Value":3716,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":16,"Level":2,"Children":null,"Id":"c2bd3e18-7c80-4309-a15b-403549dec1eb"},
         {"Text":"泰州市","Value":3212,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":8,"Level":2,"Children":null,"Id":"3cf5a785-a5d3-4b9b-a652-c95112b3a3ac"},
         {"Text":"南平市","Value":3507,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":6,"Level":2,"Children":null,"Id":"602f0669-1eed-4ed1-a8c9-07ce8fb0e144"},
         {"Text":"珠海市","Value":4404,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":6,"Level":2,"Children":null,"Id":"5fdf44ee-3d80-49d3-ba69-7bee99102db4"},
         {"Text":"海口市","Value":4601,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":6,"Level":2,"Children":null,"Id":"844d9e0e-b5c6-4d0b-9d5d-db8cb2ac50aa"},
         {"Text":"无锡市","Value":3202,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":5,"Level":2,"Children":null,"Id":"66797192-0cf3-413e-a783-387fa296d8e0"},
         {"Text":"扬州市","Value":3210,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":4,"Level":2,"Children":null,"Id":"cc9a47ab-95dd-4d23-a714-98ad8c514e85"},
         {"Text":"杭州市","Value":3301,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":4,"Level":2,"Children":null,"Id":"3e62176d-fdc6-4b95-9cb5-4c55ddb7f699"},
         {"Text":"台州市","Value":3310,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":4,"Level":2,"Children":null,"Id":"e0498687-c124-417a-85b8-eb40228ff290"},
         {"Text":"亳州市","Value":3416,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":4,"Level":2,"Children":null,"Id":"4432d90a-4f11-4f0f-9816-82184a5d6137"},
         {"Text":"石家庄市","Value":1301,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"f21a6780-4774-4e9e-8c26-7a81e30b1396"},
         {"Text":"温州市","Value":3303,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"2e572b64-8aee-47de-9d23-063d43e94f1f"},
         {"Text":"嘉兴市","Value":3304,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"beb8e066-d53f-4225-a5b3-e27482438685"},
         {"Text":"衢州市","Value":3308,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"a33e4f68-547a-4447-bddf-346c510f61b7"},
         {"Text":"合肥市","Value":3401,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"af79c392-b05d-4a7d-81b1-40e80a75ef17"},
         {"Text":"广州市","Value":4401,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"f91f8b7e-caef-4d6b-87c3-fbcbc8a3e434"},
         {"Text":"毕节市","Value":5224,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":3,"Level":2,"Children":null,"Id":"9a62117e-1dc4-4c0f-8d2a-0cac46585374"},
         {"Text":"闵行区","Value":3110,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":2,"Level":2,"Children":null,"Id":"a17a73a4-47d4-40aa-b4d5-62e75bdd8479"},
         {"Text":"湖州市","Value":3305,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":2,"Level":2,"Children":null,"Id":"408132a4-f566-4698-8f2d-0b8435974676"},
         {"Text":"保亭黎族苗族自治县","Value":4616,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":2,"Level":2,"Children":null,"Id":"ef93dddd-d610-4354-9bcb-269209aa7d20"},
         {"Text":"丰台区","Value":1105,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"dc3ca802-a38c-43cf-9f06-9846026b3657"},
         {"Text":"南京市","Value":3201,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"5595f64e-42b9-422a-9be2-be4d2c8a3dcc"},
         {"Text":"苏州市","Value":3205,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"f31b75cd-e9cf-4dd2-a2ec-351c6969d6d8"},
         {"Text":"宁波市","Value":3302,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"a7a85f2f-1c0a-4d94-aa39-32b2865ffe9b"},
         {"Text":"青岛市","Value":3702,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"411ed9f3-118a-42ed-92f7-a9c0b5a1aff6"},
         {"Text":"德州市","Value":3714,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"64a9b0ae-6bed-44e3-8c4f-f468de88f07b"},
         {"Text":"聊城市","Value":3715,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"9aed1d7c-9c25-4676-a351-435207012912"},
         {"Text":"咸阳市","Value":6104,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":2,"Children":null,"Id":"15bf9ed7-609a-4338-b736-a1053c5660d2"},
         {"Text":"禅城区","Value":440601,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":3,"Children":null,"Id":"15bf9ed7-609a-4338-b736-a1053c5660d2"},
         {"Text":"芙蓉区","Value":430101,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":3,"Children":null,"Id":"15bf9ed7-609a-4338-b736-a1053c5660d2"},
         {"Text":"别德马","Value":20101,"Letter":null,"AllLetter":null,"FullParentPath":null,"Count":1,"Level":1,"Children":null,"Id":"15bf9ed7-609a-4338-b736-a1053c5660d2"}
         ];	*/
	var temp=[];
	for(var i in workPlace) temp[workPlace[i].Value]=workPlace[i];
	workPlace=temp;
	$.getJSON('https://const.italent.cn/api/v2/compatible/value/Areas/100000/chs/151',{},function(areas){
		//console.log(areas);
		var list=[];
		for(var i in workPlace){
			if(workPlace[i].Level == 1){ //省份改变PID
				workPlace[i].Pid=0;
			}else if(workPlace[i].Level == 2){ //从城市源头找到省份
				var isLevel=false;
				for(var i2 in areas){
					for(var i3 in areas[i2].children){
						if(parseInt(areas[i2].children[i3].code) == parseInt(i)){
							workPlace[i].Pid=areas[i2].code;
							workPlace[areas[i2].code]={
								Text:areas[i2].name,
								Value:areas[i2].code,
								Letter:null,
								AllLetter:null,
								FullParentPath:null,
								Count:0,
								Level:2,
								Children:null,
								Pid:0,
							};
							//console.log(areas[i2].children[i3].fullPathCode);
							break;
						}
					}
					if(isLevel) break;
				}
			}else if(workPlace[i].Level == 3){ //从区县源头找到城市找到省份
				var isLevel=false;
				for(var i2 in areas){
					for(var i3 in areas[i2].children){
						for(var i4 in areas[i2].children[i3].children){
							if(parseInt(areas[i2].children[i3].children[i4].code) == parseInt(i)){
								//console.log(areas[i2].children[i3].children[i4].name);
								workPlace[i].Pid=areas[i2].children[i3].code;
								//省份
								workPlace[areas[i2].code]={
									Text:areas[i2].name,
									Value:areas[i2].code,
									Letter:null,
									AllLetter:null,
									FullParentPath:null,
									Count:0,
									Level:1,
									Children:null,
									Pid:0,
								};
								//城市
								workPlace[areas[i2].children[i3].code]={
									Text:areas[i2].children[i3].name,
									Value:areas[i2].children[i3].code,
									Letter:null,
									AllLetter:null,
									FullParentPath:null,
									Count:0,
									Level:2,
									Children:null,
									Pid:areas[i2].code,
								};
								isLevel=true;
								break;
							}
						}
						if(isLevel) break;
					}
					if(isLevel) break;
				}
			}
		}
		workPlace = make.recurrence(workPlace,'Pid','Value','Children',0);
		//console.log(workPlace);
		make.node('#__workPlace_search__').setData({workPlace:workPlace});
		$('#__workPlace_search__').show();
	});
};
//获取检索条件[平铺]
make.getJobAdConditions=function(){
	var param={
		Category:make.getData().query.Category,
		PageId:make.getData().query.PageId,
		displayFilters:[
			"LocId",
			"ClassificationOne",
			"ClassificationTwo",
			"Classification3"
		]
	};
	make.request('/api/JobAd/GetJobAdConditions','post',param,function(result){
		var workPlace=[];
		var positionCategory=[];
		var department=[];
		var Classification3 = [];
		if(result.Code == 200){
			for(var i in result['Data']){
				//工作地点
				if(result['Data'][i].Value == 'LocId') workPlace=result['Data'][i].Data;
				//职位分类
				if(result['Data'][i].Value == 'ClassificationOne') positionCategory=result['Data'][i].Data;
				//招聘部门
				if(result['Data'][i].Value == 'ClassificationTwo') department=result['Data'][i].Data;
				// 机构类型
				if(result['Data'][i].Value == 'Classification3') Classification3=result['Data'][i].Data;
			}
		}

		//工作地点
		make.node('#__workPlace_search__').setData({workPlace:workPlace});
		$('#__workPlace_search__').show();
		//招聘部门
		make.node('#__department_search__').setData({department:department});
		//职位分类
		make.node('#__positionCategory_search__').setData({positionCategory:positionCategory});
		//职位发布时间
		make.node('#__PostDate_search__').setData({});
		//关键字检索
		make.node('#__keywords_search__').setData({});

		// 机构类型
		make.node('#__institutional_search__').setData({Classification3:Classification3});

		$('#__department_search__,#__positionCategory_search__,#__PostDate_search__,#__keywords_search__,#__institutional_search__').show();
	});
};

//测试获取指定类型的树型数据[仅供测试使用]
make.testTreeType=function(param){
	make.request('/api/JobAd/SearchJobClassConditions','get',param,function(result){
		console.log(result);
	});
};

// 获取检索条件[树型：机构类型] 2024年9月10日
make.getClassification3=function () {
	var param={
		"SearchType": "Classification3",
		"KeyWord": "",
		"CategoryId": parseInt(make.getData().query.Category)
	}
	make.request('/api/JobAd/SearchJobClassConditions','get',param,function(result){
		var Data=result['Data'] ? result['Data'] : [];
		make.getData().tempClassification3=Data;
		make.setClassification3();
	});
}


//获取检索条件[树型：招聘单位]
make.getClassificationTwo=function(){
	var param={
		"SearchType": "ClassificationTwo",
		"KeyWord": "",
		"CategoryId": parseInt(make.getData().query.Category)
	}
	make.request('/api/JobAd/SearchJobClassConditions','get',param,function(result){
		var Data=result['Data'] ? result['Data'] : [];
		make.getData().tempClassificationTwo=Data;
		make.getClassificationTwoSet();
	});
};
make.getClassificationTwoSet=function(){
	var Data= make.getData().tempClassificationTwo;
	var cftwo=make.getData().query.ClassificationTwo;
	console.log('hhhh',Data)
	if(!Data){ //平铺模式
		Data=make.getData().department;
		for(var i in Data){
			if(Data[i].Value == cftwo) {
				Data[i].now=true;
				break;
			}
		}
	}else{ //多级分类模式
		for(var i in Data){
			if(Data[i].key == cftwo) Data[i].now=true;
			if(Data[i].children){
				for(var i2 in Data[i].children){
					if(Data[i].children[i2].key == cftwo) {
						Data[i].now=true;
						Data[i].children[i2].now=true;
					}
					if(Data[i].children[i2].children){
						for(var i3 in Data[i].children[i2].children){
							if(Data[i].children[i2].children[i3].key == cftwo){
								Data[i].now=true;
								Data[i].children[i2].now=true;
								Data[i].children[i2].children[i3].now=true;
							}
						}
					}
				}
			}
		}
	}
	//console.log(Data);
	make.node('#__department_search__').setData({department:Data});
	$('#__department_search__').show();
};

//获取检索条件[树型：职位分类]，有职位分类的才被获取
make.getClassificationOne=function(){
	var param={
		"SearchType": "ClassificationOne",
		"KeyWord": "",
		"CategoryId": parseInt(make.getData().query.Category)
	}
	make.request('/api/JobAd/SearchJobClassConditions','get',param,function(result){
		var Data=result['Data'] ? result['Data'] : [];
		make.getData().tempPositionCategory=Data;
		make.getClassificationOneSet();
	});
};
//获取全部[树型：职位分类] 不需要有职位分类也能被获取
make.getClassificationOne2=function(){
	var param={
		"TypeCode":1 //1全部招聘分类，2全部区域
	}
	make.request('/api/OpenCustomization/GetJobAdCustomTypeList','POST',param,function(result){
		var Data=result['Data'] ? result['Data'] : {};
		Data=Data.Type ? Data.Type : {};
		var list=Data.Items ? Data.Items : [];
		var Data=[];
		for(var i in list){
			if(!Data[i]) Data[i]={};
			Data[i].key=list[i].Value;
			Data[i].title=list[i].Text;
			Data[i].children=[];
			if(list[i].Items){
				for(var i2 in list[i].Items){
					Data[i].children[i2]={key:list[i].Items[i2].Value,title:list[i].Items[i2].Text,children:[]};
					if(list[i].Items[i2].Items){
						for(var i3 in list[i].Items[i2].Items){
							Data[i].children[i2].children[i3]={key:list[i].Items[i2].Items[i3].Value,title:list[i].Items[i2].Items[i3].Text,children:[]};
						}
					}
				}
			}
		}
		make.getData().tempPositionCategory=Data;
		make.getClassificationOneSet();
	});
};

// 2024年9月10日
make.getClassification3Set=function(){
	var Data= make.getData().tempClassification3;
	var cfone=make.getData().query.Classification3;
	if(!Data){ //平铺模式
		Data=make.getData().Classification3;
		for(var i in Data){
			if(Data[i].Value == cfone){
				Data[i].now=true;
				break;
			}
		}
	}else{ //多级分类模式
		for(var i in Data){
			if(Data[i].key == cfone) Data[i].now=true;
			if(Data[i].children){
				for(var i2 in Data[i].children){
					if(Data[i].children[i2].key == cfone){
						Data[i].now=true;
						Data[i].children[i2].now=true;
					}
					if(Data[i].children[i2].children){
						for(var i3 in Data[i].children[i2].children){
							if(Data[i].children[i2].children[i3].key == cfone){
								Data[i].now=true;
								Data[i].children[i2].now=true;
								Data[i].children[i2].children[i3].now=true;
							}
						}
					}
				}
			}
		}
	}

	//console.log(Data);
	make.node('#__institutional_search__').setData({Classification3:Data});
	$('#__institutional_search__').show();
};

make.getClassificationOneSet=function(){
	var Data= make.getData().tempPositionCategory;
	var cfone=make.getData().query.ClassificationOne;
	if(!Data){ //平铺模式
		Data=make.getData().positionCategory;
		for(var i in Data){
			if(Data[i].Value == cfone){
				Data[i].now=true;
				break;
			}
		}
	}else{ //多级分类模式
		for(var i in Data){
			if(Data[i].key == cfone) Data[i].now=true;
			if(Data[i].children){
				for(var i2 in Data[i].children){
					if(Data[i].children[i2].key == cfone){
						Data[i].now=true;
						Data[i].children[i2].now=true;
					}
					if(Data[i].children[i2].children){
						for(var i3 in Data[i].children[i2].children){
							if(Data[i].children[i2].children[i3].key == cfone){
								Data[i].now=true;
								Data[i].children[i2].now=true;
								Data[i].children[i2].children[i3].now=true;
							}
						}
					}
				}
			}
		}
	}

	//console.log(Data);
	make.node('#__positionCategory_search__').setData({positionCategory:Data});
	$('#__positionCategory_search__').show();
};

//获取检索条件[树型：招聘区域]
make.getRegion=function(){
	var param={
		categoryId:parseInt(make.getData().query.Category)
	};
	make.request('/api/JobAd/SearchAreasTreeConditions','get',param,function(result){
		var Data=result['Data'] ? result['Data'] : [];
		for(var i in Data) if(Data[i].ParentCode == '') Data[i].ParentCode="0";
		Data=make.recurrence(Data,'ParentCode','Code','Children',0);
		make.getData().tempWorkPlace=Data ? Data : [];
		make.getRegionSet();
	});
};
make.getRegionSet=function(){
	var Data= make.getData().tempWorkPlace;
	var tempLocld=make.getData().query.LocId;
	if(!Data){ //平铺模式
		Data= make.getData().workPlace;
		for(var i in Data){
			if(Data[i].Value == tempLocld) {
				Data[i].now=true;
				break;
			}
		}
	}else{//多级分类模式
		for(var i in Data){
			if(Data[i].Code == tempLocld) Data[i].now=true;
			for(var i2 in Data[i].Children){
				if(Data[i].Children[i2].Code == tempLocld){
					Data[i].now=true;
					Data[i].Children[i2].now=true;
				}
				for(var i3 in Data[i].Children[i2].Children){
					if(Data[i].Children[i2].Children[i3].Code == tempLocld){
						Data[i].now=true;
						Data[i].Children[i2].now=true;
						Data[i].Children[i2].Children[i3].now=true;
					}
				}
			}
		}
	}
	make.node('#__workPlace_search__').setData({workPlace:Data});
	$('#__workPlace_search__').show();
};

//获取职位列表
make.getJobAdPageList=function(e){

	if(make.getData().isLoad || make.getData().loadComplete) return;
	make.setLoads();
	var query={};
	for(var i in make.getData().query) {
		if(make.getData().query[i] || make.getData().query[i] == '0') {
			//if(i == 'KeyWords') query[i]=make.urlencode(make.getData().query[i]);
			if(i == 'KeyWords') query[i]=make.getData().query[i];
			else query[i]=make.getData().query[i];
		}

	}
	make.request('/api/Jobad/GetJobAdPageList','post',query,function(data){
		var Count=0;
		var list=[];
		if(data.Code == 200){
			Count=parseInt(data.Count);
			list = data.Data;
			//完全没有数据
			if(parseInt(make.getData().query.PageIndex) == 0 && list.length <= 0) make.getData().notData=true;
			else make.getData().notData=false;
			for(var i in list) {
				list[i].PostDate=make.timestampToTime(list[i].PostDateInt);
				list[i].EndTime=list[i].EndTimeInt  ? make.timestampToTime(list[i].EndTimeInt) : '';
				list[i].Duty=list[i].Duty.replace("\n","<br />");
				list[i].Require=list[i].Require.replace("\n","<br />");
			}
			if(make.getData().isPageAppend) make.getData().list=make.getData().list.concat(list);
			else make.getData().list=list;

			//是否加载完成全部数据
			if(parseInt(make.getData().query.PageIndex) > 0 && list.length <= 0) make.getData().loadComplete=true;
			else make.getData().loadComplete=false;
		}
		if(!make.getData().isPageAppend) make.setPage(Count);
		make.closeLoads();
		make.getData().isFirstLoad=true;
		make.node('#__category_banner__').setData({});
		$('#__category_banner__').show();
		make.node('#__JobAdList__').setData({});
		$('#__JobAdList__').show();
		if(make.getData().PrevPage > 0){
			if(!make.getData().isPageAppend) make.goMarginTop();
		}

	});
};
//获取热招职位
make.getHotJobAdList=function(){
	var query={};
	for(var i in make.getData().query) {
		if(make.getData().query[i] || make.getData().query[i] == '0') {
			if(i == 'KeyWords') query[i]=make.getData().query[i];
			else query[i]=make.getData().query[i];
		}
	}
	make.request('/api/Jobad/GetJobAdPageList','post',query,function(data){
		var list=[];
		if(data.Code == 200){
			list = data.Data;
			for(var i in list) {
				list[i].PostDate=make.timestampToTime(list[i].PostDateInt);
				list[i].Duty=list[i].Duty.replace("\n","<br />");
				list[i].Require=list[i].Require.replace("\n","<br />");
			}
		}
		make.node('#__HotJobAdList__').setData({hotJobAdList:list});
		$('#__HotJobAdList__').show();
	});
};
//获取分页
make.getPage=function(number){
	make.getData().PrevPage=make.getData().query.PageIndex == 0 ? 1 : make.getData().query.PageIndex;
	make.getData().query.PageIndex=number;
	make.getJobAdPageList();
};
//输入页码
make.getPage2=function(){
	var number=$('#__entry_page__').val();
	if(isNaN(number) || number < 1){
		$('#__entry_page__').val('').focus();
		return false;
	}
	make.getData().PrevPage=make.getData().query.PageIndex == 0 ? 1 : make.getData().query.PageIndex;
	number--;
	make.getData().query.PageIndex=number;
	make.getJobAdPageList();
	return false;
}
//筛选职位类型
make.getCategory=function(_this,value,jump){
	jump = arguments[2] ? arguments[2] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var val=$(_this).val();
	value=val ? val : value;
	if(jump){
		var url=window.location.pathname;
		url+="?Category="+value+"&Category_name=";
		url+="&ClassificationTwo="+make.getQueryString("ClassificationOne")+"&ClassificationTwoName="+make.getQueryString("ClassificationTwoName");
		url+="&ClassificationOne="+make.getQueryString("ClassificationOne")+"&ClassificationOneName="+make.getQueryString("ClassificationOneName");
		url+="&LocId="+make.getQueryString("LocId")+"&LocIdName="+make.getQueryString("LocIdName");
		url+="&KeyWords="+make.getQueryString("KeyWords");
		url+="&PostDate="+make.getQueryString("PostDate");
		window.location.href=url;
		return;
	}
	make.getData().query.Category=value ? [value] : [];
	var query=make.getData().query;
	make.node('#__category_search__').setData({query:query});
	make.getJobAdPageList();
};
//筛选招聘部门
make.setDepartment=function(_this,value,jump){

	jump = arguments[2] ? arguments[2] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var val=$(_this).val();
	value=val ? val : value;
	if(jump){
		var url=window.location.pathname;
		url+="?ClassificationTwo="+value+"&ClassificationTwoName=";
		url+="&Category="+make.getQueryString("Category")+"&CategoryName="+make.getQueryString("CategoryName");
		url+="&ClassificationOne="+make.getQueryString("ClassificationOne")+"&ClassificationOneName="+make.getQueryString("ClassificationOneName");
		url+="&LocId="+make.getQueryString("LocId")+"&LocIdName="+make.getQueryString("LocIdName");
		url+="&KeyWords="+make.getQueryString("KeyWords");
		url+="&PostDate="+make.getQueryString("PostDate");
		window.location.href=url;
		return;
	}
	make.getData().query.ClassificationTwo=value;
	var query=make.getData().query;
	make.node('#__department_search__').setData({query:query});
	make.getClassificationTwoSet();
	make.getJobAdPageList();
};
//职位分类筛选
make.setPosition=function(_this,value,jump){

	jump = arguments[2] ? arguments[2] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var val=$(_this).val();
	value=val ? val : value;

	if(jump){
		var url=window.location.pathname;
		url+="?ClassificationOne="+value+"&ClassificationOneName=";
		url+="&Category="+make.getQueryString("Category")+"&CategoryName="+make.getQueryString("CategoryName");
		url+="&ClassificationTwo="+make.getQueryString("ClassificationTwo")+"&ClassificationTwoName="+make.getQueryString("ClassificationTwoName");
		url+="&LocId="+make.getQueryString("LocId")+"&LocIdName="+make.getQueryString("LocIdName");
		url+="&KeyWords="+make.getQueryString("KeyWords");
		url+="&PostDate="+make.getQueryString("PostDate");
		window.location.href=url;
		return;
	}

	make.getData().query.ClassificationOne=value;
	var query=make.getData().query;
	make.node('#__positionCategory_search__').setData({query:query});
	make.getClassificationOneSet();
	make.getJobAdPageList();
};

//职位分类3筛选 2024年9月10日
make.setClassification3=function(_this,value,jump){

	jump = arguments[2] ? arguments[2] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var val=$(_this).val();
	value=val ? val : value;

	if(jump){
		var url=window.location.pathname;
		url+="?ClassificationOne="+value+"&ClassificationOneName=";
		url+="&Category="+make.getQueryString("Category")+"&CategoryName="+make.getQueryString("CategoryName");
		url+="&ClassificationTwo="+make.getQueryString("ClassificationTwo")+"&ClassificationTwoName="+make.getQueryString("ClassificationTwoName");
		url+="&LocId="+make.getQueryString("LocId")+"&LocIdName="+make.getQueryString("LocIdName");
		url+="&KeyWords="+make.getQueryString("KeyWords");
		url+="&PostDate="+make.getQueryString("PostDate");
		window.location.href=url;
		return;
	}

	make.getData().query.Classification3=value;
	var query=make.getData().query;
	make.node('#__institutional_search__').setData({query:query});
	make.getClassification3Set();
	make.getJobAdPageList();
};

//区域筛选
make.setWorkPlace=function(_this,value,jump){
	jump = arguments[2] ? arguments[2] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var val=$(_this).val();
	value=val ? val : value;
	if(jump){
		var url=window.location.pathname;
		url+="?LocId="+value+"&LocIdName=";
		url+="&Category="+make.getQueryString("Category")+"&CategoryName="+make.getQueryString("CategoryName");
		url+="&ClassificationTwo="+make.getQueryString("ClassificationTwo")+"&ClassificationTwoName="+make.getQueryString("ClassificationTwoName");
		url+="&ClassificationOne="+make.getQueryString("ClassificationOne")+"&ClassificationOneName="+make.getQueryString("ClassificationOneName");
		url+="&KeyWords="+make.getQueryString("KeyWords");
		url+="&PostDate="+make.getQueryString("PostDate");
		window.location.href=url;
		return;
	}
	make.getData().query.LocId=value;
	var query=make.getData().query;
	make.node('#__workPlace_search__').setData({query:query});
	make.getRegionSet();
	make.getJobAdPageList();
};
//职位发布时间筛选
make.setPostDate=function(_this,value,jump){
	jump = arguments[2] ? arguments[2] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var val=$(_this).val();
	value=val ? val : value;
	if(jump){
		var url=window.location.pathname;
		url+="?PostDate="+value;
		url+="&Category="+make.getQueryString("Category")+"&CategoryName="+make.getQueryString("CategoryName");
		url+="&LocId="+make.getQueryString("LocId")+"&LocIdName="+make.getQueryString("LocIdName");
		url+="&ClassificationTwo="+make.getQueryString("ClassificationTwo")+"&ClassificationTwoName="+make.getQueryString("ClassificationTwoName");
		url+="&ClassificationOne="+make.getQueryString("ClassificationOne")+"&ClassificationOneName="+make.getQueryString("ClassificationOneName");
		url+="&KeyWords="+make.getQueryString("KeyWords");
		window.location.href=url;
		return;
	}
	make.getData().query.PostDate=value;
	var query=make.getData().query;
	make.node('#__PostDate_search__').setData({query:query});
	make.getJobAdPageList();
};
//关键字筛选
make.getKeywords=function(jump){
	jump = arguments[0] ? arguments[0] : '';
	make.getData().query.PageIndex=0;
	make.getData().loadComplete=false;
	make.getData().list=[];
	var KeyWords=$('#__keywords__').val();
	if(KeyWords) KeyWords=make.htmlToEscape(KeyWords);
	if(jump){
		var url=window.location.pathname;
		url+="?KeyWords="+KeyWords;
		url+="&Category="+make.getQueryString("Category")+"&CategoryName="+make.getQueryString("CategoryName");
		url+="&LocId="+make.getQueryString("LocId")+"&LocIdName="+make.getQueryString("LocIdName");
		url+="&ClassificationTwo="+make.getQueryString("ClassificationTwo")+"&ClassificationTwoName="+make.getQueryString("ClassificationTwoName");
		url+="&ClassificationOne="+make.getQueryString("ClassificationOne")+"&ClassificationOneName="+make.getQueryString("ClassificationOneName");
		url+="&PostDate="+make.getQueryString("PostDate");
		window.location.href=url;
		return;
	}
	make.getData().query.KeyWords=KeyWords;
	make.getJobAdPageList();
	return false;
};
//获取职位详情
make.getJobAdInfo=function(){
	make.setLoads();
	var query={
		jobAdId:make.getQueryString('jobAdId'),
		displayFields:'["jobAdName","Duty","Require","Category","Kind","LocId","PostDate","Org","HeadCount","YearsOfWorking","Degree","Salary","ClassificationTwo","ClassificationOne","Classification3","Classification4","Classification5","Classification6","Channel4SequenceNumber","EndTime"]',
		PortalId:make.getData().PortalId
	};
	make.request('/api/JobAd/GetJobAdInfo','get',query,function(data){
		if(data.Code == 200){

			// 2024年7月14日 地点数组转字符串
			if (data.Data.LocNames) {
				var locNamestr = data.Data.LocNames.join(", "); // 使用逗号和空格作为分隔符
				data.Data.LocNames = locNamestr;
			}

			if(data.Data.PostDateInt) data.Data.PostDate=make.timestampToTime(data.Data.PostDateInt);
			if(data.Data.EndTimeInt) data.Data.EndTime = make.timestampToTime(data.Data.EndTimeInt);
			else data.Data.EndTime='';
			//if(data.Data.Duty) data.Data.Duty=data.Data.Duty.replace("\n","<br />");
			//if(data.Data.Require) data.Data.Require=data.Data.Require.replace("\n","<br />");
			//招聘公司
			var ClassificationTwo=make.getQueryString('ClassificationTwo');
			ClassificationTwo=ClassificationTwo != 'null' ? ClassificationTwo : '';
			data.Data.ClassificationTwo=data.Data.ClassificationTwo ? data.Data.ClassificationTwo : '';
			data.Data.ClassificationTwo=ClassificationTwo ? ClassificationTwo : data.Data.ClassificationTwo;
			//职位分类
			var ClassificationOne=make.getQueryString('ClassificationOne');
			ClassificationOne=ClassificationOne != 'null' ? ClassificationOne : '';
			data.Data.ClassificationOne=data.Data.ClassificationOne ? data.Data.ClassificationOne : '';
			data.Data.ClassificationOne=ClassificationOne ? ClassificationOne : data.Data.ClassificationOne;

			// 2024年8月14日 社招取自定义字段
			if (data.Data.CategoryId == 1) {
				var query2={
					JobAdIds:make.getQueryString('jobAdId'),
					CustomFields: 'extzhaopingonggao_603177_628790293'
				};
				make.request('/api/OpenCustomization/GetJobCustomFields','post',query2,function(newData) {
					if (newData.Code == 200) {
						if (newData.Data[0].CustomFields.extzhaopingonggao_603177_628790293) {
							// data.Data.ZiDingYi = newData.Data[0].CustomFields.extzhaopingonggao_603177_628790293;
							$('#ZiDingYi').text( newData.Data[0].CustomFields.extzhaopingonggao_603177_628790293 );
						}
					}
				})
			}

			make.getData().result=data.Data;
			make.getData().query.Category=data.Data.CategoryId ? [data.Data.CategoryId] : [];

			// 是否收藏
			var IsCollect = data.Data.IsCollect;
			if (IsCollect == true) {
				// 手机
				$('.sczw').addClass('sczw_now');
				// PC
				$('.xqicon1b').addClass('xqicon1b_now');
			} else {
				// 手机
				$('.sczw').removeClass('sczw_now');
				// PC
				$('.xqicon1b').removeClass('xqicon1b_now');
			}



		}
		make.isFirstLoad=true;
		make.node('#__category_banner__').setData({});
		$('#__category_banner__').show();
		make.node('#__Job_Details__').setData({});
		$('#__Job_Details__').show();
		make.closeLoads();
	});
};
/**收藏/取消收藏
 * remind  如果是函數运行指定函數，如果有值弹窗提示，无任何值时只改变样式不作其它处理
 */
make.collectPosition=function(remind){
	remind = arguments[0] ? arguments[0] : '';
	if(make.getData().isLoad) return;
	make.setLoads();
	var jobAdId=make.getQueryString('jobAdId');
	make.login('#__user_login__',function(result){
		if(result['Code'] != 200 || !result['Data']['UserId']){
			make.closeLoads();
			location.href = '/login?goto='+make.getData().loginURL;
			return;
		}
		var query={
			jobAdId:jobAdId
		};
		if(make.getData().result.IsCollect) var path='/api/JobAd/DeleteJobCollect';
		else path='/api/JobAd/JobAdCollect';

		make.request(path,'get',query,function(res){
			make.closeLoads();



			if(res.Code == 200){

				// 2024年7月14日 新增在这里判断是收藏还是取消收藏
				if(make.getData().result.IsCollect) {
					$('.sczw').addClass('sczw_now');
					console.log('收藏成功111');
				} else {
					$('.sczw').removeClass('sczw_now');
					console.log('取消收藏成功1111');
				}
				// 成功后重新执行
				make.getJobAdInfo()

				make.getData().result.IsCollect=!make.getData().result.IsCollect;
				make.node('#__Job_Details__').setData({});
				if(typeof remind == "function"){
					remind(make.getData().result.IsCollect);
					return;
				}else if(remind){
					if(make.getData().result.IsCollect) {
						console.log('收藏成功');
						alert('收藏成功');
					} else {
						console.log('取消收藏成功');
						alert('取消收藏成功');
					}
				}
			}else{
				alert(res.Message);
			}
		});
	});
};
//申请职位
make.applyPosition=function(){
	var that=make;
	that.setLoads();
	var jobAdId=that.getQueryString('jobAdId');
	that.login('#__user_login__',function(result){
		make.closeLoads();
		if(result['Code'] != 200 || !result['Data']['UserId']){
			location.href = '/login?goto='+make.getData().loginURL;
			return;
		}
		//投递后返回列表
		//如果未能获取到返回列表路径将自动跳转 /jobs 标品页，然后通过设置路由方式重定向跳转指定一列
		var referrer=document.referrer;
		var origin = document.location.origin;
		var gotoUrl='';
		if(referrer.indexOf(origin) > -1){
			if(referrer.indexOf(document.location.pathname) == -1) gotoUrl=make.urlencode(referrer.replace(origin+'/',''));
		}
		location.href = '/form?hideMenu=1&fromPage=job&jobAdId='+jobAdId+'&activityGuid='+activityGuid+'&userId='+result['Data']['UserId']+'&goto='+gotoUrl
	});
};
//微信分享
var interIntNuber=0;
make.wxShare=function(jobDesc){
	//详情页分享
	if(jobDesc){
		interIntNuber = setInterval(function(){
			var result=make.getData().result ? make.getData().result : {};
			if(result.Id){
				make.wxShareGet();
				clearInterval(interIntNuber);
			}
		},1000);
		return;
	}
	//其它页面分享
	make.wxShareGet();
};
make.wxShareGet=function(){
	var jobAdId=make.getQueryString("jobAdId");
	if(jobAdId) var param={jobAdId:jobAdId};
	else var param={};
	var url = window.location.href.split('#')[0];
	url = url.replace('/\&/g','$26');
	make.request('/api/JobAd/GetJsSdkInitInfo','get',{url:url},function(res){
		var Data=res.Data;
		wx.config({
			debug: false, // 开启调试模式,调用的所有api的返回值会在客户端alert出来，若要查看传入的参数，可以在pc端打开，参数信息会通过log打出，仅在pc端时才会打印。
			appId: Data.AppId, // 必填，公众号的唯一标识
			timestamp: Data.TimeStamp, // 必填，生成签名的时间戳
			nonceStr:Data.Nonce, // 必填，生成签名的随机串
			signature: Data.Sign,// 必填，签名
			jsApiList: [  // 必填，需要使用的JS接口列表
				'updateAppMessageShareData',
				'updateTimelineShareData',
				'onMenuShareTimeline',
				'onMenuShareAppMessage'
			]
		});
		//获取分享内容
		$.getJSON('/api/JobAd/GetShareSetting',param,function(ret){
			//console.log(ret);
			var Data=ret.Data;
			wx.ready(function () {   //需在用户可能点击分享按钮前就先调用
				//分享图片
				// var allShareImg=make.getData().allShareImg ? make.getData().allShareImg : Data.DfsPath;
				var allShareImg = 'https://yuege-beijing.oss-cn-beijing.aliyuncs.com/chinastock/phimg/sharelogo.jpg';
				//详情页职位数据
				var result=make.getData().result ? make.getData().result : {};
				if(result.Id){
					var title='向您推荐'+result.JobAdName;
					var desc='地点:'+result.LocNames[0]+'\n薪资:'+(result.Salary ? result.Salary : '面议');
				}else{
					var title='向您推荐'+document.title;
					if(!title)  title=Data.Subtitle ? Data.Subtitle : (Data.CompanyShortName ? Data.CompanyShortName :'');
					if(!title)  title=Data.MainTitle ? Data.MainTitle : '';
					var desc=(Data.CompanyShortName ? Data.CompanyShortName : '')+(Data.MainTitle ? Data.MainTitle : '');
					if(!desc) desc='欢迎您的加入!';
				}
				//分享到朋友圈
				wx.onMenuShareTimeline({
					title: title,
					desc: desc,
					link:  url, // 分享的url
					imgUrl: allShareImg, // 分享的图标url
					trigger: function (res) {}, //分享成功
					success: function (res) {},
					cancel: function (res) {},
					fail: function (res) {}
				});
				// 自定义“分享给朋友”及“分享到QQ”按钮的分享内容（1.4.0） 2022年5月19日11:26:29
				wx.updateAppMessageShareData({
					title: title, // 分享标题
					desc: desc, // 分享描述
					link: url, // 分享链接，该链接域名或路径必须与当前页面对应的公众号 JS 安全域名一致
					imgUrl: allShareImg, // 分享图标
					success: function () {},
					cancel: function (res) {},
					fail: function (res) {}
				});
				//分享给朋友
				wx.onMenuShareAppMessage({
					title: title,
					desc:desc,
					link:  url, //分享的url
					imgUrl:allShareImg, // 图标url
					trigger: function (res) {},
					success: function (res) {}, //分享成功
					cancel: function (res) {},
					fail: function (res) {}
				});
				//分享朋友圈
				wx.updateTimelineShareData({
					title: title,
					desc: desc,
					link:  url, //分享的url
					imgUrl:allShareImg, // 图标url
					trigger: function (res) {},
					success: function (res) {},//分享成功后执行
					cancel: function (res) {},
					fail: function (res) {}
				});
			});
			wx.error(function(res){
				//alert(res);
				console.log('wx.error',res);
				// config信息验证失败会执行error函数，如签名过期导致验证失败，具体错误信息可以打开config的debug模式查看，也可以在返回的res参数中查看，对于SPA可以在这里更新签名。
			});
		});
	});
}
//切换语言[参考中金]
//参数：0中文，2英文
make.setLanguage=function(language){
	language = arguments[0] ? arguments[0] : 0;
	var path='/api/Common/SetLanguage?language='+language;
	make.request(path,'get',{},function(res){
		var url=window.location.href;
		if(url.indexOf('?') > -1) {
			if(arguments == 0) url+="&lang=ch";
			else url+="&lang=en";
		}else{
			if(arguments == 0) url+="?lang=ch";
			else url+="?lang=en";
		}
		window.location.href=url;
	});
}
