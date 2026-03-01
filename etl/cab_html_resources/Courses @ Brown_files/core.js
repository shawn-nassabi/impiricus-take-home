
const sam = {};
sam.login = function login() {
	if (sam.user.isAuthenticated()) {
		return Promise.resolve();
	}

	sam.auth.launch();

	return new Promise(function (resolve) {
		sam.events.once(
			sam.events.EVENT_LOGIN,
			function () {
				resolve();
				return Promise.resolve();
			}
		);
	});
};
sam.isAuthenticated = function isAuthenticated() {
	return sam.user.isAuthenticated();
};
sam.fetchRecord = function fetchRecord() {
	if (sam.auth.isModeToken()) {
		sam.auth.restoreToken();

		if (!sam.auth.token) {
			return Promise.resolve();
		}
	}

	return sam.user.fetch()
		.catch(function () { /* intentional no-op */ });
};
sam.restoreRecord = function restoreRecord() {
	return sam.user.restore();
};
sam.lookupMajor = function lookupMajor(code) {
	return sam.config.majorCodeToName[code];
};
window.setAuthToken = function setAuthToken(token, expires, options) {
	sam.auth.setToken(token, expires, options);
};
window.closeAuthWindow = function closeAuthWindow() {
	sam.auth.closeAuthWindow();
	window.focus();
};


sam.config = function () {
	'use strict';

	const exports = {
		authURL: '',
		authWindowFeatures: '',
		userRecordURL: '',
		cartURL: '',
		isFuse: false,
		shockAbsorberURL: '',
		textHead: 'Authentication',
		textWaiting: 'Waiting for user authentication...',
		textBusy: 'Checking user authentication...',
		textError: 'Authentication was not successful.  Please try again.',
		textNoToken: 'No authentication token was provided.',
		textPrimaryCart: 'Primary',
		funcSetRecord: 'setRecord',
		funcSetCart: 'setCart',
		tokenParameter: 'authpin',
		sessionTimeout: 86400,
		skipShockAbsorber: {},
		areCartsByCareer: false,
		showEmptyCareerCarts: false,
		excludeRegisteredFromPreflight: false,
		preserveP_: false,
		majorCodeToName: {},
		levelCodeToName: {}
	};
	const oldPropertyToNewProperty = {
		multiplePrimaryCarts: 'areCartsByCareer',
		levels: 'levelCodeToName',
		majors: 'majorCodeToName'
	};

	for (let oldProperty in oldPropertyToNewProperty) {
		const newProperty = oldPropertyToNewProperty[oldProperty];
		Object.defineProperty(
			exports,
			oldProperty,
			{
				get: function () {
					return this[newProperty];
				},
				set: function (value) {
					this[newProperty] = value;
				}
			}
		);
	}

	return exports;
}();


sam.util = function () {
	'use strict';

	const REGEX_CONSTANT = /^[A-Z0-9_]+$/;

	const exports = {
		freezeConstants: function freezeConstants(obj) {
			for (let key in obj) {
				if (REGEX_CONSTANT.test(key)) {
					Object.defineProperty(
						obj,
						key,
						{
							value: obj[key],
							enumerable: true,
							configurable: false,
							writable: false
						}
					);
				}
			}
		},
		isPlainObject: function isPlainObject(value) {
			return Object.prototype.toString.call(value) === '[object Object]';
		}
	};

	return exports;
}();



var lf = lf || {};
lf.cache = lf.cache || {};
lf.cache.Cache = lf.cache.Cache || function() {
	'use strict';

	function Cache() {
		this._cache = new Map();
		this._cachedAt = new Map();
		this._cacheResultKey = {};
	}
	Cache.prototype.withCache = function (fn, thisArg, options) {
		var self = this;
		options = options || {};
		options.isAsync = false;
		return function () {
			var args = [fn, thisArg, options].concat(
				Array.prototype.slice.call(arguments)
			);

			return self._call.apply(self, args);
		}
	}
	Cache.prototype.withCacheAsync = function (fn, thisArg, options) {
		var self = this;
		options = options || {};
		options.isAsync = true;
		return function () {
			var args = [fn, thisArg, options].concat(
				Array.prototype.slice.call(arguments)
			);

			return self._call.apply(self, args);
		}
	}
	function mapHas(cMap, rKey) {
		for (var i = 2; i < arguments.length; i++) {
			cMap = cMap.get(arguments[i]);
			if (!cMap) return false;
		}

		return cMap.has(rKey);
	}
	function mapGet(cMap, rKey) {
		for (var i = 2; i < arguments.length; i++) {
			cMap = cMap.get(arguments[i]);
			if (!cMap) return undefined;
		}

		return cMap.get(rKey);
	}
	function mapSet(cMap, rKey, value) {
		var oMap = cMap;
		for (var i = 3; i < arguments.length; i++) {
			if (!cMap.has(arguments[i])) cMap.set(arguments[i], new Map());
			cMap = cMap.get(arguments[i]);
		}

		cMap.set(rKey, value);
		return oMap;
	}
	Cache.prototype.has = function (fn, thisArg) {
		return mapHas.apply(null, [this._cache, this._cacheResultKey].concat(Array.prototype.slice.call(arguments)));
	}
	Cache.prototype.get = function (fn, thisArg) {
		return mapGet.apply(null, [this._cache, this._cacheResultKey].concat(Array.prototype.slice.call(arguments)));
	}
	Cache.prototype.set = function (value, fn, thisArg) {
		mapSet.apply(null, [this._cache, this._cacheResultKey, value].concat(Array.prototype.slice.call(arguments, 1)));
		mapSet.apply(null, [this._cachedAt, this._cacheResultKey, Date.now()].concat(Array.prototype.slice.call(arguments, 1)));
		return true;
	}
	Cache.prototype._call = function (fn, thisArg, options) {
		var self = this;

		options = options || {};
		options.maxAge = typeof options.maxAge === 'number' ? options.maxAge : -1;
		options.force = typeof options.force === 'boolean' ? options.force : false;
		options.isAsync = typeof options.isAsync === 'boolean' ? options.isAsync : false;

		var fnArgs = Array.prototype.slice.call(arguments, 0, 2).concat(Array.prototype.slice.call(arguments, 3));
		var isCached = self.has.apply(self, fnArgs);
		var isExpired = !isCached || options.maxAge === -1 || options.force;

		if (!isExpired) {
			isExpired = mapGet.apply(self, [this._cachedAt, this._cacheResultKey].concat(fnArgs)) + options.maxAge < Date.now();
		}

		switch (true) {
			case isExpired && !options.isAsync:
				var result = fn.apply(thisArg, fnArgs.slice(2));
				self.set.apply(self, [result].concat(fnArgs));
				return self.get.apply(self, fnArgs);
			case !isExpired && !options.isAsync:
				return self.get.apply(self, fnArgs);
			case isExpired && options.isAsync:
				console.log("Cache Miss");
				return Promise
					.resolve(fn.apply(thisArg, fnArgs.slice(2)))
					.then(function (result) {

						self.set.apply(self, [result].concat(fnArgs));
						return Promise.resolve(self.get.apply(self, fnArgs));
					})
					.catch(function (ex) {
						throw ex;
					});
			case !isExpired && options.isAsync:
				console.log("Cache Hit");
				return Promise.resolve(self.get.apply(self, fnArgs));
			default:
				throw "Unexpected Error"
		}
	}

	return Cache;
}();


sam.cache = sam.cache || lf.cache;


sam.url = function () {
	'use strict';

	const exports = {
		addParameters: function addParameters(url, parameters) {
			if (!sam.util.isPlainObject(parameters)) {
				return url;
			}

			const parts = Object.keys(parameters).map(function (key) {
				var value = parameters[key];
				if (typeof value === 'undefined') value = "";
				if (typeof value.toString !== 'function') value = "";
				return encodeURIComponent(key) + '=' + encodeURIComponent(value.toString());
			});

			if (parts.length === 0) {
				return url;
			}

			const baseURL = base(url);
			const hadParams = baseURL === url;
			let newParams = '';

			if (hadParams && baseURL.substr(-1) !== '&') {
				newParams = '&';
			}

			newParams += parts.join('&');

			return baseURL + newParams;
		},
		addParameter: function addParameter(url, key, value) {
			if (!url || !key || key === '') {
				return url;
			}
			const parameters = {};
			parameters[key] = value || '';

			return sam.url.addParameters(url, parameters);
		},
		appendParameter: function appendParameter(url, key, value) {
			return this.addParameter(url, key, value);
		}
	};
	function base(url) {
		if (url.indexOf('?') === -1) {
			return url + '?';
		}
		return url;
	}

	return exports;
}();


sam.fetch = function () {
	'use strict';

	const DEFAULT_MAX_WAIT = 20000;
	const POSTED_TOKEN_NAMES = ['authtoken','access_token'];
	function withImpersonation( url, postdata ) {
		if ( url && sam.record ) {
			const rawPerson = sam.record.rawProperty('pers') || {};
			if ( postdata ) {
				postdata._pers_id = rawPerson.id;
				postdata._pers_id_proof = rawPerson.idProof;
				postdata._pers_real_id = rawPerson.realuser || rawPerson.id;
			}
			if ( /.+\?.*\bwho\=/.test(url) ) {
				return url;
			}
			if ( sam.record.isImpersonating() ) {
				url = sam.url.addParameter(url, "who", rawPerson.id);
			}
		}
		return url;
	};

	const exports = {
		jsonp: function jsonp(url, funcName, maxWait) {
			return new Promise(function (resolve,reject) {
				let didTimeout = false;
				const timeout = setTimeout(
					function () {
						didTimeout = true;
						resolve({error: 'Request did not complete successfully.  Please try again.'});
					},
					maxWait || DEFAULT_MAX_WAIT
				);

				if (sam.auth.token) {
					url = sam.url.addParameter(url, sam.config.tokenParameter, sam.auth.token);
				}
				url = withImpersonation( url );

				$.ajax({
					url,
					dataType: 'jsonp',
					jsonp: false,
					cache: true,
					jsonpCallback: funcName
				}).then(
					function (response, status, xhr) {
						return $.Deferred().resolve(response, status, xhr);
					},
					function (xhr, status, err) {
						if (xhr.responseText && status === "parsererror") {
							var reString = "(?:^" + funcName.replace(/[^A-Za-z0-9]/g, "") + "\\(|\\)$)";
							var replaceRe = new RegExp(reString, "g");
							try {
								var response = xhr.responseText.replace(replaceRe, "");
								response = JSON.parse(response);
								return $.Deferred().resolve(response, "success", xhr);
							} catch (ex) {
								return $.Deferred().reject(xhr, status, new Error(ex));
							}
						}
						return $.Deferred().reject(xhr, status, err);
					}
				).then(
					function (response, status, xhr) {
						clearTimeout(timeout);
						if (!didTimeout) {
							response = sam.fetch.extractError(response);
							resolve(response);
						}
					},
					function (xhr, status, err) {
						console.log(err);
						resolve({ error: err }); // better than reject(err) for compatibility with existing code
					}
				);
			});
		},
		jsonCompat: function jsonCompat (url, funcName) {
			funcName = funcName || "";
			return new Promise(function (resolve,reject) {
				var postIt = {};

				if (sam.auth.token) {
					postIt[sam.config.tokenParameter] = sam.auth.token;
				}
				url = withImpersonation( url, postIt );

				$.ajax({
					type: "POST",
					url: url,
					dataType: "text",
					data: postIt
				}).done(function (txt, status, xhr) {
					var response = sam.fetch.extractJsonpResponse( txt, funcName );
					resolve(response);
				}).fail(function (xhr, status, err) {
					console.log(arguments);
					resolve({ error: err }); // better than reject(err) for compatibility with existing code
				});
			});
		},
		extractJsonpResponse: function extractJsonpResponse( responseText, funcName ) {
			responseText = (responseText || '').split('\n').join(' ').trim();
			var reString = "(?:^" + funcName.replace(/[^A-Za-z0-9_]/g, "") + "\\(|\\);?$)";
			var replaceRe = new RegExp(reString, "g");
			var response = responseText.replace(replaceRe, "");
			response = JSON.parse(response);
			response = sam.fetch.extractError(response);
			return response;
		},
		dispatchJson: function (url, funcName) {
			if ( ~POSTED_TOKEN_NAMES.indexOf(sam.config.tokenParameter) ) {
				return exports.jsonCompat.apply(this, arguments);
			}
			return exports.jsonp.apply(this, arguments);
		},
		json: function json(url) {
			return new Promise(function (resolve,reject) {
				var postIt = {};
				if (sam.auth.token) {
					postIt[sam.config.tokenParameter] = sam.auth.token;
				}
				url = withImpersonation( url, postIt );

				$.ajax({
					type: "POST",
					url: url,
					dataType: 'json',
					data: postIt,
				}).done (function(response) {
					resolve(response);
				}).fail (function (xhr, status, err) {
					console.log(arguments);
					resolve({ error: err }); // better than reject(err) for compatibility with existing code
				});
			})
		},
		extractError: function extractError(response) {
			if (Array.isArray(response.error)) {
				response.error = response.error.map(
					function (err) {
						if (err && sam.util.isPlainObject(err) && 'usermsg' in err) {
							return err.usermsg;
						}
						response.fatal = response.fatal || typeof err.fatal === 'undefined' || !!err.fatal;

						return err;
					}
				).join('\n');
			}

			return response;
		}
	};

	return exports;
}();


sam.events = function () {
	'use strict';
	const handlerRegistry = {};
	function initEvent(event) {
		if (!handlerRegistry[event]) {
			handlerRegistry[event] = {
				on: [],
				once: []
			};
		}
	}

	const exports = {
		EVENT_LOGIN: 'login',
		EVENT_LOGOUT: 'logout',
		EVENT_GOT_CART: 'got-cart',
		EVENT_GOT_RECORD: 'got-record',
		on: function on(event, handler) {
			initEvent(event);
			handlerRegistry[event].on.push(handler);
		},
		off: function off(event, handler) {
			if (!handlerRegistry[event]) {
				return;
			}

			handlerRegistry[event].on = handlerRegistry[event].on.filter(function (h) {
				return h !== handler;
			});

			handlerRegistry[event].once = handlerRegistry[event].once.filter(function (h) {
				return h !== handler;
			});
		},
		once: function once(event, handler) {
			initEvent(event);
			handlerRegistry[event].once.push(handler);
		},
		emit: function emit(event, args) {
			const handlers = [];

			if (handlerRegistry[event]) {
				handlerRegistry[event].on.forEach(function (handler) {
					handlers.push(handler);
				});

				handlerRegistry[event].once.forEach(function (handler) {
					handlers.push(handler);
				});

				handlerRegistry[event].once = [];
			}

			args = Array.prototype.slice.call(arguments, 1);
			const start = [];

			return handlers.reduce(function (promiseChain, handler) {
				return promiseChain.then(function (chainResults) {
					const result = handler.apply(window, args);
					if (result && result.then) {
						return result.then(function (currentResult) {
							chainResults.push(currentResult);
							return chainResults;
						});
					} else {
						chainResults.push(result);
						return chainResults;
					}
				});
			}, Promise.resolve(start))
		},

		s: {
			emit: function emit(event, args) {
				const handlers = [];

				if (handlerRegistry[event]) {
					handlerRegistry[event].on.forEach(function (handler) {
						handlers.push(handler);
					});

					handlerRegistry[event].once.forEach(function (handler) {
						handlers.push(handler);
					});

					handlerRegistry[event].once = [];
				}

				args = Array.prototype.slice.call(arguments, 1);

				return handlers.reduce(function (pv, handler) {
					pv.push(handler.apply(window, args));
					return pv;
				}, [])
			}
		}
	};

	sam.util.freezeConstants(exports);

	return exports;
}();


sam.dialog = function () {
	'use strict';
	let domDialog;
	let dialogRenderer;
	let dialogTemplate = '';
	let isVisible = false;

	const DOM_ID = 'sam-wait';
	const CLASS_CLOSE = DOM_ID + '__close';
	const CLASS_BUTTON_CANCEL = DOM_ID + '__button--cancel';
	const CLASS_BUTTON_LOGIN = DOM_ID + '__button--login';
	const SELECTOR_CANCEL = '.' + CLASS_BUTTON_CANCEL;

	const exports = {
		EVENT_CLICK_CANCEL: 'dialog.click-cancel',
		EVENT_CLICK_LOGIN: 'dialog.click-login',
		setTemplate: function setTemplate(source) {
			dialogTemplate = source;
		},
		initialize: function initialize() {
			if (domDialog) return;

			dialogRenderer = lfjs.stache.compile(dialogTemplate);

			domDialog = /** @type {LFJSWindow} */(document.createElement('div'));
			domDialog.setAttribute('id', DOM_ID);
			domDialog.classList.add(DOM_ID);
			domDialog.classList.add('screen');
			domDialog.addEventListener('click', this.handleClicks);

			document.body.append(domDialog);

			new lfjs.window(domDialog);
		},
		handleClicks: function handleClicks(event) {
			const target = /** @type {HTMLElement} */(event.target);
			if (!target) return;

			const cl = target.classList;

			if (cl.contains(CLASS_BUTTON_CANCEL) || cl.contains(CLASS_CLOSE)) {
				lfjs.keypress.stuff('ESC');
			} else if (cl.contains(CLASS_BUTTON_LOGIN)) {
				lfjs.keypress.stuff('Ctrl+ENTER');
			}
		},
		show: function show() {
			this.initialize();
			this.setWaitingState();

			if (isVisible) return;
			domDialog.activate({keyhandler: this.keyhandler});
			isVisible = true;
		},
		keyhandler: function keyhandler(key) {
			switch (key) {
				case 'Ctrl+ENTER':
					sam.events.emit(sam.dialog.EVENT_CLICK_LOGIN);
					return false;

				case 'ESC':
					sam.events.emit(sam.dialog.EVENT_CLICK_CANCEL);
					return false;
			}

			return true;
		},
		hide: function hide() {
			if (!isVisible) return;
			domDialog.deactivate();
			isVisible = false;
		},
		setWaitingState: function setWaitingState() {
			this.setState({
				message: sam.config.textWaiting
			});
		},
		setBusyState: function setBusyState() {
			this.setState({
				message: sam.config.textBusy,
				busy: true
			});
		},
		setErrorState: function setErrorState(error) {
			this.setState({
				message: sam.config.textError,
				error: error
			});
		},
		setState: function setState(state) {
			const templateData = Object.assign({}, state);
			templateData.id = DOM_ID;
			templateData.config = sam.config;

			const html = dialogRenderer.render(templateData);
			domDialog.innerHTML = html;
		},
		focus: function focus() {
			if (domDialog.contains(document.activeElement)) return;
			const el = domDialog.querySelector(SELECTOR_CANCEL);
			if (el) el.focus();
		}
	};

	sam.util.freezeConstants(exports);

	return exports;
}();


sam.auth = function () {
	'use strict';

	const exports = {
		TOKEN_COOKIE: 'samauthtoken',

		AUTH_MODE_TOKEN: 'token',
		AUTH_MODE_COOKIE: 'cookie',
		token: undefined,
		tokenExpires: sam.config.sessionTimeout,
		authWindow: null,
		isModeToken: function isModeToken() {
			return authMode === this.AUTH_MODE_TOKEN;
		},
		isModeCookie: function isModeCookie() {
			return authMode === this.AUTH_MODE_COOKIE;
		},
		getMode: function getMode() {
			return authMode;
		},
		setMode: function setMode(mode) {
			switch (mode) {
				case this.AUTH_MODE_COOKIE:
				case this.AUTH_MODE_TOKEN:
					authMode = mode;
					break;

				default:
					throw new Error('Unknown authentication mode');
			}
		},
		finish: function finish() {
			sam.dialog.hide();
			isInProgress = false;
		},
		launch: function launch() {
			isInProgress = true;
			sam.dialog.show();
			this.openAuthWindow();
		},
		handleWindowFocus: function handleWindowFocus() {
			if (!isInProgress) return;

			this.closeAuthWindow();

			if (this.isModeToken() && !this.token) {
				sam.dialog.setErrorState(sam.config.textNoToken);
				return;
			}

			sam.dialog.setBusyState();
			sam.user.fetch().then(function () {
					sam.auth.finish();
				}).catch(function (error) {
					sam.dialog.setErrorState(error);
				});
		},
		openAuthWindow: function openAuthWindow() {
			switch (true) {
				case sam.auth.isSafariIOS13():
					window.open(
						sam.config.authURL,
						'sam-authenticate',
						sam.config.authWindowFeatures
					);
					break;
				default:
					sam.auth.authWindow = window.open(
						sam.config.authURL,
						'sam-authenticate',
						sam.config.authWindowFeatures
					);
			}

			if (!this.authWindow) {
				return;
			}

			this.authWindow.focus();
		},
		isSafariIOS13: function isSafariIOS13() {
			var userAgent = window.navigator.userAgent;
			var isIOS = (/iPhone|iPod|iPad/).test(userAgent);
			var isWebkit = (/WebKit/).test(userAgent);
			var isNotExcluded = !(/CriOS|OPiOS|FxiOS/).test(userAgent);
			var iosVersion = userAgent.match(/\bVersion\/(\d+).(\d+)/);
			return isIOS && isWebkit && isNotExcluded && Number((iosVersion || [])[1] || "") >= 13;
		},
		closeAuthWindow: function closeAuthWindow() {
			if (sam.auth.authWindow) {
				try {
					sam.auth.authWindow.close();
				} catch (ex) { /* Intentional no-op */}
			}

			sam.auth.authWindow = null;
		},
		setToken: function setToken(token, expires, options) {
			options = options || {};
			switch (typeof expires) {
				case 'number':
					sam.auth.tokenExpires = expires;
					break;

				case 'string': {
					const exp = parseInt(expires, 10);
					if (!isNaN(exp)) {
						sam.auth.tokenExpires = exp;
					}
					break;
				}
			}

			this.token = token;
			if ( !options.skipSave ) {
				sam.auth.saveToken();
			}
		},
		clearToken: function clearToken() {
			sam.auth.token = undefined;
			document.cookie = exports.TOKEN_COOKIE + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
		},
		saveToken: function saveToken() {
			if (this.token) {
				document.cookie = exports.TOKEN_COOKIE + '=' + encodeURIComponent(this.token);
			}
		},
		restoreToken: function restoreToken() {
			if (this.token) return;

			const cookies = document.cookie.split('; ');
			for (let i = 0; i < cookies.length; i++) {
				const cookie = cookies[i];
				const equalsIndex = cookie.indexOf('=');
				const cookieName = cookie.substr(0, equalsIndex);
				if (cookieName === exports.TOKEN_COOKIE) {
					const cookieValue = cookie.substr(equalsIndex + 1);
					this.token = decodeURIComponent(cookieValue);
					break;
				}
			}
		}
	};

	sam.util.freezeConstants(exports);

	sam.events.on(
		sam.dialog.EVENT_CLICK_CANCEL,
		function () {
			exports.finish();
			return Promise.resolve();
		}
	);

	sam.events.on(
		sam.dialog.EVENT_CLICK_LOGIN,
		function () {
			exports.launch();
			return Promise.resolve();
		}
	);

	window.addEventListener(
		'focus',
		function () {
			exports.handleWindowFocus();
		}
	);

	let authMode = exports.AUTH_MODE_COOKIE;
	let isInProgress = false;

	return exports;
}();


sam.user = function() {
	'use strict';

	const STORAGE_KEY = 'sam-user-record';
	let rawRecord;
	let user = {
		id: '',
		name: '',
		isInstructor: false,
		level: undefined,
		classification: '',
		termLevels: {},
		majors: [],
		colleges: [],
		taken: {},
		planned: {},
		plans: {},
		overrides: {},
		blacklist: {},
		whitelist: {},
		waitlist: {
			lookup: {},
			lookupByCareer: {},
			byTerm: {},
			position: {}
		},
		registered: {
			courses: {},
			sections: {},
			sectionsByCareer: {},
		},
		stashData: {},
		myManagedKeyword: "",
	};
	function fail( msg ) {
		throw new Error( msg );
	};

	let realUsersByToken = {};
	const applyRealuserHack = function applyRealuserHack( record ) {
		if ( record.pers && record.pers.id && !record.pers.realuser ) {
			if ( realUsersByToken[ sam.auth.token ] ) {
				if ( realUsersByToken[ sam.auth.token ] != record.pers.id ) {
					record.pers.realuser = realUsersByToken[ sam.auth.token ];
				}
			}
			else {
				realUsersByToken[ sam.auth.token ] = record.pers.id;
			}
		}
	};

	const exports = {
		internalData() {
			return JSON.parse( JSON.stringify( user ) );
		},
		stash() {
			return user.stashData;
		},
		fetch: function fetch() {
			if (!sam.config.userRecordURL) {
				throw new Error('No userRecordURL has been set');
			}

			let userRecordURL = sam.config.userRecordURL;
			if (sam.config.isFuse || sam.auth.isModeToken()) {
				userRecordURL = sam.url.addParameter(userRecordURL, 'action', 'studentdata')
			}

			return sam.fetch
				.dispatchJson(userRecordURL, sam.config.funcSetRecord)
				.then(
					function (response) {
						return sam.user
							.setRawRecord(response)
							.finally(function () {
								if (response.error) {
									return Promise.reject(response.error);
								} else {
									return Promise.resolve();
								}
							});
					});
		},
		id: function id() {
			return user.id;
		},
		name: function name() {
			return user.name;
		},
		isInstructor: function isInstructor() {
			return user.isInstructor;
		},
		myManagedKeyword: function myManagedKeyword() {
			if (user.myManagedKeyword && user.myManagedKeyword.length > 0) return user.myManagedKeyword;
			return sam.user.id();
		},
		classification: function classification() {
			return user.classification;
		},
		isLinkBlacklisted: function isLinkBlacklisted(term, lfams) {
			if (!lfams) {
				return false;
			}

			const parts = lfams.split(/([;,])/);
			let groupOk = false;

			for (let i = 0; i < parts.length; i++) {
				const part = parts[i];
				if (part === ';') {
					if (!groupOk) {
						return true;
					}
					groupOk = false;
				} else if (part !== ',' && !this.isBlacklisted(term, part)) {
					groupOk = true;
				}
			}

			return !groupOk;
		},
		isWhitelisted: function isWhitelisted(term, rfam) {
			if (isNaN(parseInt(rfam, 10))) {
				return true;
			}
			return term + '-' + rfam in user.whitelist;
		},
		isBlacklisted: function isBlacklisted(term, rfam) {
			return term + '-' + rfam in user.blacklist;
		},
		blacklistReasons: function blacklistReasons(term, rfam) {
			return user.blacklist[term + '-' + rfam];
		},
		hasOverride: function hasOverride(term, crn) {
			return term + '-' + crn in user.overrides;
		},
		hasTaken: function hasTaken(code) {
			const taken = user.taken[code];
			return taken && !taken.isEquiv;
		},
		hasTakenInTerm: function hasTakenInTerm(term,code) {
			const taken = user.taken[code];
			return taken && !taken.isEquiv && -1 !== taken.inTerms.indexOf(term);
		},
		hasTakenEquiv: function hasTakenEquiv(code) {
			const taken = user.taken[code];
			return taken && taken.isEquiv;
		},
		takenCodes: function takenCodes() {
			return Object.keys(user.taken);
		},
		plannedCodes: function plannedCodes() {
			return Object.keys(user.planned);
		},
		allPlans: function allPlans() {
			return user.plans;
		},
		isWaitlisted: function isWaitlisted(term, crn) {
			return !!user.waitlist.lookup[term + '-' + crn];
		},
		waitlistPosition: function waitlistPosition(term, crn) {
			return user.waitlist.position[term + '-' + crn];
		},
		waitlistSections: function waitlistSections(term, cartID) {
			cartID = cartID || "";
			var forCareer = "";
			if (cartID && sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(sam.cart.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					forCareer = cartID.substr(delimiter + 1);
				}
			}
			switch(true) {
				case forCareer !== "":
					var sections = [];
					for (const key in user.waitlist.lookupByCareer) {
						if (!user.waitlist.lookupByCareer.hasOwnProperty(key)) continue;
						const [career, keyTerm, crn] = key.split('-');
						if (forCareer !== career) continue;
						if (term !== keyTerm) continue;
						sections.push(crn);
					}
					return sections;
				default:
					return user.waitlist.byTerm[term] || [];
			}
		},
		isRegistered: function isRegistered(term, crn) {
			return !!user.registered.sections[term + '-' + crn];
		},
		isRegisteredInTermForCourse: function isRegisteredInTermForCourse(term, courseCode) {
			return !!user.registered.coursesInTerm[term + '-' + courseCode];
		},
		registeredSections: function registeredSections(forTerm, cartID) {
			cartID = cartID || "";
			var forCareer = "";
			if (cartID && sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(sam.cart.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					forCareer = cartID.substr(delimiter + 1);
				}
			}
			const sections = [];

			switch (true) {
				case forCareer !== "":
					for (const key in user.registered.sectionsByCareer) {
						if (!user.registered.sectionsByCareer.hasOwnProperty(key)) continue;
						const [career, term, crn] = key.split('-');
						if (forCareer !== career) continue;
						if (forTerm !== term) continue;
						sections.push(crn);
					}
					break;
				default:
					for (const key in user.registered.sections) {
						if (!user.registered.sections.hasOwnProperty(key)) continue;
						const [term, crn] = key.split('-');
						if (forTerm !== term) continue;
						sections.push(crn);
					}
					break;
			}

			return sections;
		},
		registeredCodes: function registeredCodes() {
			return Object.keys(user.registered.courses);
		},
		historicalSections: function historicalSections(forTerm) {
			var hist = (rawRecord || {}).hist || {};
			return (hist[forTerm] || []).map(function(x) { return (x||'').split('|')[3]; });
		},
		currentColleges: function currentColleges() {
			return user.colleges;
		},
		termLevels: function termLevels(term) {
			if (!term) {
				term = '';
			}

			if (user.termLevels[term]) {
				return user.termLevels[term];
			}

			if (user.level) {
				return [user.level];
			}
			const allLevels = {};
			for (const key in user.termLevels) {
				if (user.termLevels.hasOwnProperty(key)) {
					for (let i = 0; i < user.termLevels[key].length; i++) {
						const level = user.termLevels[key][i];
						allLevels[level] = true;
					}
				}
			}

			return Object.keys(allLevels);
		},
		isValidTermLevel: function isValidTermLevel(term, level) {
			const levels = user.termLevels[term];
			if (!levels) return false;

			return levels.indexOf(level) !== -1;
		},
		latestMajors: function latestMajors() {
			if (user.majors.length === 0) {
				return [];
			}

			const last = user.majors[user.majors.length - 1];
			return last.codes;
		},
		isAuthenticated: function isAuthenticated() {
			return rawRecord !== undefined;
		},
		isImpersonating: function isImpersonating() {
			const rawPerson = this.getProperty('pers') || {};
			return rawPerson.id && rawPerson.realuser && rawPerson.realuser !== rawPerson.id;
		},
		setRawRecord: function setRawRecord(record) {
			if (!record || record.error) {
				this.clear();
				return Promise.resolve([]);
			}

			applyRealuserHack( record );

			const wasAuthenticated = this.isAuthenticated();
			this.save(record);
			parseRawRecord(record);
			return sam.events
				.emit(sam.events.EVENT_GOT_RECORD)
				.then(function () {
					if (!wasAuthenticated) {
						return sam.events.emit(sam.events.EVENT_LOGIN);
					} else {
						return Promise.resolve([]);
					}
				});
		},
		reloadRawRecord: function reloadRawRecord() {
			return sam.user.setRawRecord(rawRecord);
		},
		save: function save(record) {
			rawRecord = record;

			let sessionData = getSessionRecord();
			if (sessionData) {
				let stashData = (sessionData.record || {}).stashData || {};
				if (sessionData.record.pers.id !== record.pers.id) {
					stashData = {};
				}
				record.stashData = stashData;
				sessionData.record = record;
			} else {
				sessionData = {
					timestamp: Date.now(),
					record
				};
			}

			sessionStorage.setItem(STORAGE_KEY, JSON.stringify(sessionData));
		},
		restore: function restore() {
			const sessionData = getSessionRecord();
			if (sessionData) {
				this.setRawRecord(sessionData.record);
			}
		},
		clear: function clear() {
			const wasLoggedIn = this.isAuthenticated();

			rawRecord = undefined;
			sessionStorage.removeItem(STORAGE_KEY);
			sam.auth.clearToken();

			if (wasLoggedIn) {
				sam.events.emit(sam.events.EVENT_LOGOUT);
			}
		},
		rawProperty: function rawProperty(prop) {
			return this.getProperty(prop);
		},
		getProperty: function getProperty(prop) {
			if (!rawRecord || !(prop in rawRecord)) {
				return;
			}

			return rawRecord[prop];
		},
		updateProperty: function updateProperty(prop, value) {
			if (rawRecord) {
				if ( '@' == prop[0] ) { // partial update
					Object.assign( rawRecord[prop.slice(1)], value );
				}
				else {
					rawRecord[prop] = value;
				}
				this.save(rawRecord);
				_sanitizeRawRecord(rawRecord);
			}
		}
	};
	exports.updatePlansFromRawRecord = function updatePlansFromRawRecord( rawRecord ) {
		user || fail( "Not signed in" );
		Object.assign( user, parsePlanned( (rawRecord || {}).plan || [] ) );
	};


	const regexCRN = /^\d+$/;
	const regexBlacklistTermPrefix = /^CB_/;
	function getSessionRecord() {
		const json = sessionStorage.getItem(STORAGE_KEY);
		if (!json) return;

		try {
			const sessionData = JSON.parse(json);
			const now = Date.now();
			const expired = now > sessionData.timestamp + sam.config.sessionTimeout * 1000;

			if (!expired) {
				return sessionData;
			}

			sessionStorage.removeItem(STORAGE_KEY);
		} catch (ex) {
			sessionStorage.removeItem(STORAGE_KEY);
		}
	}
	function _sanitizeRawRecord(record) {
		function inHist(term,crn) {
			var hist = record.hist || {};
			return (hist[term] || []).some(function(x) { return crn == (x||'').split('|')[3]; });
		};
		function inReg(term,crn) {
			var reg = record.reg || {};
			return (reg[term] || []).some(function(x) { return crn == (x||'').split('|')[0]; });
		};
		function remove_( item, reason ) {
			console.log( '[CART cleanup] Removing stale or ineffective item from CART because '+ reason +': ', item );
		};
		function trimTrailingDashFromPipedPart( arr, pipedPart ) {
			arr.forEach( function(x,i) {
				var parts = (x||'').split('|');
				if ( '-' == parts[ pipedPart ].slice(-1) ) {
					parts[ pipedPart ] = parts[ pipedPart ].slice(0,-1);
					arr[ i ] = parts.join('|');
				}
			});
		};
		Object.keys( record.hist || {} ).forEach( function(term) {
			trimTrailingDashFromPipedPart( record.hist[ term ], 0 );
		});
		Object.keys( record.reg || {} ).forEach( function(term) {
			trimTrailingDashFromPipedPart( record.reg[ term ], 1 );
		});
		if ( record.cart ) {
			trimTrailingDashFromPipedPart( record.cart, 7 );
			record.cart = record.cart.filter( function(x) {
				var parts = (x||'').split('|');
				if ( inHist( parts[0], parts[2] ) ) {
					remove_( x, 'the class is already taken' );
					return false;
				}
				if ( -1 !== ['','E'].indexOf( parts[12] ) && inReg( parts[0], parts[2] ) ) {;
					remove_( x, 'the class is already registered' );
					return false;
				}
				return true;
			});
		}
		return; // 2022-08-05 cancelled

		if ( record.reg ) {
			Object.keys( record.reg ).forEach( function(term) {
				record.reg[ term ] = record.reg[ term ].filter( function(x) {
					var crn = (x||'').split('|')[0];
					return !inHist(term,crn);
				});
			});
		}
	};
	function parseRawRecord(record) {
		_sanitizeRawRecord( record );

		const person = record.pers || {};
		user.name = person.fn;
		user.id = person.id;
		user.level = person.levl;
		user.classification = person.clas;
		user.isInstructor = person.inst;
		user.myManagedKeyword = person.mymanaged_keyword || "";

		const current = parseCurrent(person.cur);
		user.majors = current.majors;
		user.termLevels = current.levels;

		user.taken = parseTaken(record.hist || {});
		exports.updatePlansFromRawRecord( record );
		user.colleges = parseColleges(person.coll);
		user.waitlist = parseWaitlist(record.waitlist || {});
		user.blacklist = parseBlacklist(record.bl || {});
		user.whitelist = parseWhitelist(record.wl || {});
		user.overrides = parseOverrides(
			record.override || {},
			record.permReq || {}
		);
		user.registered = parseRegistered(record.reg || {});
	}
	function parseWhitelist(whitelist) {
		const parsed = {};

		for (const rawTerm in whitelist) {
			const term = rawTerm.replace(regexBlacklistTermPrefix, '');

			for (let i = 0; i < whitelist[rawTerm].length; i++) {
				const rfam = whitelist[rawTerm][i];
				parsed[term + '-' + rfam] = true;
			}
		}

		return parsed;
	}
	function parseBlacklist(blacklist) {
		const parsed = {};

		for (const rawTerm in blacklist) {
			const term = rawTerm.replace(regexBlacklistTermPrefix, '');
			for (const why in blacklist[rawTerm]) {
				for (let i = 0; i < blacklist[rawTerm][why].length; i++) {
					const rfam = blacklist[rawTerm][why][i];
					const key = term + '-' + rfam;
					if (!(key in parsed)) {
						parsed[key] = [];
					}

					parsed[key].push(why);
				}
			}
		}

		return parsed;
	}
	function parseOverrides(override, permReq) {
		const overrides = {};

		for (const term in override) {
			for (let i = 0; i < override[term].length; i++) {
				const crn = override[term][i];
				overrides[term + '-' + crn] = true;
			}
		}

		for (const term in permReq) {
			for (const crn in permReq[term]) {
				const req = permReq[term][crn];
				if (req.rovr_code && req.rovr_code.length > 0) {
					overrides[term + '-' + crn] = true;
				}
			}
		}

		return overrides;
	}
	function parseWaitlist(waitlist) {
		const result = {
			lookup: {},
			lookupByCareer: {},
			byTerm: {},
			position: {}
		};

		for (const term in waitlist) {
			if (waitlist.hasOwnProperty(term)) {
				for (let i = 0; i < waitlist[term].length; i++) {
					const item = waitlist[term][i];
					const parts = item.toString().split('|');
					const crn = parts[0];
					const career = parts[1];
					const position = parts[2];

					result.lookup[term + '-' + crn] = true;
					result.position[term + '-' + crn] = position;

					if (!result.byTerm[term]) {
						result.byTerm[term] = [];
					}

					if (career) {
						result.lookupByCareer[career + '-' + term + '-' + crn] = true;
					}

					result.byTerm[term].push(crn);
				}
			}
		}

		return result;
	}
	function parseRegistered(registered) {
		const result = {
			courses: {},
			coursesInTerm: {},
			sections: {},
			sectionsByCareer: {},
		};

		for (const term in registered) {
			if (registered.hasOwnProperty(term)) {
				for (let i = 0; i < registered[term].length; i++) {
					const item = registered[term][i];
					const parts = item.toString().split('|');
					let crn = parts[0];
					let code = parts[1];
					let career = parts[5];
					if (regexCRN.test(code)) {
						const temp = code;
						code = crn;
						crn = temp;
					}

					result.sections[term + '-' + crn] = true;

					if (code) {
						result.courses[code] = true;
						result.coursesInTerm[term + '-' + code] = true;
					}

					if (career) {
						result.sectionsByCareer[career + '-' + term + '-' + crn] = true;
					}
				}
			}
		}

		return result;
	}
	function parsePlanned(plans) {
		const planned = {};
		const plansContent = {};

		for (let i = 0; i < plans.length; i++) {
			const rawPlan = plans[i];
			const parts = rawPlan.split('|');
			const version = parts.length > 7 ? 2 : 1; // minireg sends only 7 columns
			const plan = parts[0];
			const subj = parts[1];
			const numb = parts[2];
			const inTerm = parts[3];
			const crn = parts[4];
			const dateAdded = version >= 2 ? parts[6] : null;
			const surrogateId = version >= 2 ? parts[7] : parts[6];
			const topic = parts[8];
			const hours = parts[9];
			const code = subj + ' ' + numb;

			planned[code] = {
				plan: plan,
				inTerm: inTerm,
				crn: crn
			};
			plansContent[ plan ] = plansContent[ plan ] || { isSnapshot: false, entries: [] };
			plansContent[ plan ].isSnapshot = sam.plan.SNAPSHOT_PREFIX == plan.slice(0,sam.plan.SNAPSHOT_PREFIX.length);
			plansContent[ plan ].entries.push({ courseCode: code, term: inTerm, surrogateId: surrogateId });
		}

		return { planned: planned, plans: plansContent };
	}
	function addTaken(taken, data) {
		if (!taken[data.code]) {
			taken[data.code] = {
				inTerms: [],
				isEquiv: data.isEquiv
			};
		}

		taken[data.code].inTerms.push(data.term);
	}
	function parseTaken(history) {
		const taken = {};

		for (const term in history) {
			if (history.hasOwnProperty(term)) {
				for (let i = 0; i < history[term].length; i++) {
					const data = history[term][i];
					const parts = data.split('|');
					const code = parts[0];
					const equivs = parts[2];
					addTaken(taken, {code: code, term: term, isEquiv: false});

					if (equivs && equivs.length > 0) {
						const splitEquivs = equivs.split(',');
						for (let j = 0; j < splitEquivs.length; j++) {
							const equiv = splitEquivs[j];
							addTaken(taken, {code: equiv, term: term, isEquiv: true});
						}
					}
				}
			}
		}

		return taken;
	}
	function parseCurrent(majors) {
		if (majors.length === 0) {
			return {majors: [], levels: {}};
		}
		const levels = {};
		const parsedMajors = [];
		const termMap = {};

		majors.forEach((data) => {
			for (const term in data) {
				if (data.hasOwnProperty(term)) {
					data[term].forEach((termData) => {
						if (!termMap[term]) {
							termMap[term] = {
								term: term,
								codes: []
							};
							parsedMajors.push(termMap[term]);
						}

						let majorCode = termData.major + '-' + termData.degc;
						if (termData.conc) {
							majorCode += '-' + termData.conc;
						}
						termMap[term].codes.push(majorCode);

						if (!levels[term]) {
							levels[term] = [];
						}

						if (levels[term].indexOf(termData.levl) === -1) {
							levels[term].push(termData.levl);
						}
					});
				}
			}
		});

		return {
			majors: parsedMajors,
			levels: levels
		};
	}
	function parseColleges(colleges) {
		if (!colleges) {
			return [];
		}

		return colleges.split(',');
	}

	return exports;
}();

sam.record = sam.user;


sam.cart = function () {
	'use strict';

	let apiTimeout = 30000;
	let readCarts = {};
	let inAnyCart = {};
	let inSpecificCart = {};
	let cartContents = {};
	let termCarts = {};

	const exports = {
		DEBUG_CART_PREFIX: '*DBG*',
		CART_CAREER_DELIMITER: '^',
		SIS_CART_ID: 'SIS_cart',
		PRIMARY_CART_ID: 'default',
		PRIMARY_CART_ID_PREFIX: 'default^',
		EVENT_GATHER_CARTS: 'cart.carts.gather',
		GATHER_TYPE_OTHERS: 'OTHERS',
		GATHER_TYPE_ALL: 'ALL',
		CONTEXT_SOURCE_KEEPALIVE: 'keepAlive',
		ROLE_KEEPALIVE: 'keepalive',
		setApiTimeout: function setApiTimeout(ms) {
			apiTimeout = ms;
		},
		preprocessParameters: function preprocessParameters(parameters) {
			parameters = parameters || {};
			let outParameters = {};

			Object.keys(parameters).forEach(function (key) {
				if (typeof parameters[key] !== "object") {
					outParameters[key] = parameters[key];
					return;
				}
				outParameters[key] = JSON.stringify(parameters[key]);
			});

			if (sam.config.preserveP_) {
				return outParameters;
			}

			Object.keys(parameters).forEach(function (key) {
				let strippedKey = key.replace(/^p_/, '');
				if (strippedKey === key) return;
				outParameters[strippedKey] = outParameters[key];
				delete outParameters[key];
			});

			return outParameters;
		},
		request: function request(parameters, context, options) {
			parameters = this.preprocessParameters(parameters);
			const url = sam.url.addParameters(sam.config.cartURL, parameters);
			context = context || {};
			context.source = context.source || "";

			options = options || {};

			return sam.fetch.dispatchJson(url, 'setCart', apiTimeout)
				.then(
					function (response) {
						var _response = typeof response === 'object' ? response : {};
						var hasError = !!_response.error;
						var isNotFatalError = hasError && !_response.fatal && typeof _response.fatal !== undefined;

						if (!('cart' in response) && !isNotFatalError) {
							sam.user.clear();
							delete response.error;
							return response;
						}

						if (hasError && isNotFatalError) {
							alert(response.error);
						}

						delete response.fatal;
						delete response.error;

						(function () {
							if (foseConfig.sis !== "banner") return;
							if (hasError) return;
							if (['cart_add', 'cart_remove'].indexOf(parameters.action) === -1) return;
							if (!response["cart"]) return;

							var cartToMerge = response["cart"] || [];
							var prefix = parameters.term_code + "|" + parameters.cart_name + "|";

							var cleanedCurrentCart = sam.user.getProperty("cart").filter(function (entry) {
								var thisPrefix = entry.split('|').slice(0, 2).join('|') + '|';
								return prefix !== thisPrefix;
							});

							response["cart"] = cleanedCurrentCart.concat(cartToMerge);
						})();

						for (let key in response) {
							sam.user.updateProperty(key, response[key]);
						}

						return sam.events
							.emit(sam.events.EVENT_GOT_CART, context)
							.then(function () {
								if (!hasError && options.emitSuccessEvent)
									sam.events.emit(options.emitSuccessEvent, parameters, context);
								if (hasError && options.emitErrorEvent)
									sam.events.emit(options.emitErrorEvent, parameters, context);
								return response;
							});
					}
				);
		},
		read: function read(context) {
			const parameters = {p_action: 'cart_read'};
			context = context || {};
			context.source = context.source || '';
			if (context.source === exports.CONTEXT_SOURCE_KEEPALIVE) {
				parameters.role = exports.ROLE_KEEPALIVE;
				var pers = sam.user.getProperty('pers') || {};
				parameters.pers_id = pers.id;
				parameters.pers_id_proof = pers.idProof;
			}
			return sam.events.emit('cart.read.before-send', parameters, context).then(function () {
				return sam.cart.request(parameters, context);
			});
		},
		add: function add(parameters, context) {
			context = context || {};
			context.source = context.source || "add";
			if (sam.config.areCartsByCareer) {
				const cartParts = parameters.p_cart_name.split(this.CART_CAREER_DELIMITER);

				if (cartParts.length === 1) {
					cartParts[1] = parameters.p_cart_level;
				}

				if (cartParts[0] === exports.SIS_CART_ID) {
					throw new Error('Reserved name, please select an alternative');
				}

				if (!sam.user.isValidTermLevel(parameters.p_term_code, cartParts[1])) {
					const firstTermLevel = sam.user.termLevels(parameters.p_term_code)[0];
					if (!firstTermLevel) {
						throw new Error('Invalid parameters');
					}
					cartParts[1] = firstTermLevel;
				}

				parameters.p_cart_name = cartParts[0] + this.CART_CAREER_DELIMITER + cartParts[1];
			}

			parameters.p_action = 'cart_add';
			return sam.events.emit('cart.add.before-send', parameters, context).then(function () {
				return sam.cart.request(parameters, context,
					{ emitSuccessEvent: 'cart.add.success', emitErrorEvent: 'cart.add.error' });
			});
		},
		remove: function remove(parameters, context) {
			parameters.p_action = 'cart_remove';
			context = context || {};
			context.source = context.source || "add";
			return sam.events.emit('cart.remove.before-send', parameters, context).then(function () {
				return sam.cart.request(parameters, context,
					{ emitSuccessEvent: 'cart.remove.success', emitErrorEvent: 'cart.remove.error' });
			});
		},
		preflight: function preflight(parameters, cartID, context) {
			parameters.p_action = 'preflight';
			const processedParameters = this.preprocessParameters(parameters);

			context = context || {};
			context.source = context.source || "preflight";
			context.cartID = cartID;
			context.term = parameters.p_term_code;
			context.parameters = processedParameters;

			if (sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(this.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					processedParameters.acad_career = cartID.substr(delimiter + 1);
				}
			}

			if (sam.config.excludeRegisteredFromPreflight) {
				var filterOutRegistered = function (crn) {
					return !sam.user.isRegistered(context.term, crn);
				}
				processedParameters.crn_list = processedParameters.crn_list
					.split(',').filter(filterOutRegistered).join(',');
			}

			return sam.events.emit('cart.preflight.before-send', processedParameters, context)
				.then(function () {
					const url = sam.url.addParameters(sam.config.cartURL, processedParameters);
					if (!processedParameters.crn_list) {
						return Promise.resolve({
							reg_course_errors: {},
							"reg_non-course_errors": [],
						})
					}
					if ( sam.config.shockAbsorberURL && !sam.config.skipShockAbsorber['preflight'] ) {
						var saParams = {};
						saParams.action = 'preflight';
						saParams.url_replay = url;
						if (sam.auth.token) {
							saParams.url_replay = sam.url.addParameter(saParams.url_replay, sam.config.tokenParameter, sam.auth.token);
						}
						const saUrl = sam.url.addParameters(sam.config.shockAbsorberURL, saParams);
						return sam.fetch.json(saUrl);
					}
					else {
						return sam.fetch.dispatchJson(url, 'preflight', apiTimeout);
					}
				}).then(
					function (result) {
						var preflightUnavailableRe = /Another registration is in progress for this ID and TERM/
						if (foseConfig.preflightUnavailableRegex) {
							preflightUnavailableRe = new RegExp(foseConfig.preflightUnavailableRegex);
						}

						var hasUnavailableError = preflightUnavailableRe.test(result.error || '');
						var isUnavailable = hasUnavailableError || !!result.isUnavailable;
						if (!isUnavailable) return result;

						var textPreflightUnavailable = "Preflight is temporarily unavailable";
						if (foseConfig.textPreflightUnavailable) {
							textPreflightUnavailable = foseConfig.textPreflightUnavailable;
						}
						var maskedResult = {
							'isUnavailable': isUnavailable,
							'reg_non-course_errors': [
								textPreflightUnavailable,
							],
							'reg_course_errors': {}
						}
						return maskedResult;
					}
				).then(
					function (result) {
						return sam.events
							.emit('cart.preflight.got-data', result, context)
							.then(function () { return result;});
					}
				).then(
					function (result) {
						if (result.error) {
							return {
								isUnavailable: !!result.isUnavailable,
								error: result.error,
								global: [],
								sections: {}
							};
						}
						const errors = {
							global: result['reg_non-course_errors'],
							sections: {},
							isUnavailable: !!result.isUnavailable,
						};

						for (let crn in result.reg_course_errors) {
							const errorParts = result.reg_course_errors[crn].split('|');
							for (let i = 0; i < errorParts.length; i++) {
								const error = errorParts[i];
								if (!error) {
									continue;
								}

								if (!errors.sections[crn]) {
									errors.sections[crn] = [];
								}
								var subParts = error.split('\n');
								subParts.forEach(function(subPart) {
									errors.sections[crn].push(subPart);
								});
							}
						}

						return errors;
					}
				);
		},
		register: function register(parameters, cartID) {
			const processedParameters = this.preprocessParameters(parameters);
			if (sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(this.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					processedParameters.acad_career = cartID.substr(delimiter + 1);
				}
			}

			return sam.events
				.emit('cart.register.before-send', processedParameters)
				.then(function () {
					const url = sam.url.addParameters(sam.config.cartURL, processedParameters);
					return sam.fetch.dispatchJson(url, 'registerResults', apiTimeout);
				});
		},
		registerSA: function registerSA(parameters, saParams, cartID) {
			const processedParameters = this.preprocessParameters(parameters);
			if (sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(this.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					processedParameters.acad_career = cartID.substr(delimiter + 1);
				}
			}

			return sam.events
				.emit('cart.register.before-send', processedParameters)
				.then(function () {
					var urlReplay = sam.url.addParameters(sam.config.cartURL, processedParameters);
					if (sam.auth.token && foseConfig.sis === "peoplesoft") {
						urlReplay = sam.url.addParameter(urlReplay, sam.config.tokenParameter, sam.auth.token);
					}

					saParams.action = 'register';
					saParams.cart_name = cartID;
					saParams.url_replay = urlReplay;

					const url = sam.url.addParameters(sam.config.shockAbsorberURL, saParams);
					return sam.fetch.json(url);
				});
		},
		queryRegisterSAStatus: function queryRegisterSAStatus(parameters, saParams, cartID) {
			const processedParameters = this.preprocessParameters(parameters);
			if (sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(this.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					processedParameters.acad_career = cartID.substr(delimiter + 1);
				}
			}

			sam.events.emit('cart.register.before-send', processedParameters);

			saParams.action = 'status';
			saParams.cart_name = cartID;

			const url = sam.url.addParameters(sam.config.shockAbsorberURL, saParams);
			return sam.fetch.json(url);
		},
		isReadOnly: function isReadOnly(cartID, term) {
			return term + '|' + cartID in readCarts;
		},
		isInSpecific: function isInSpecific(cartID, term, crn) {
			return term + '|' + cartID + '|' + crn in inSpecificCart;
		},
		isInAny: function isInAny(term, crn) {
			return term + '|' + crn in inAnyCart;
		},
		contents: function contents(cartID, term) {
			const cartTermID = term + '|' + cartID;
			if (cartContents[cartTermID]) {
				return cartContents[cartTermID];
			}

			return [];
		},
		canSubmit: function canSubmit(cartID, term) {
			return this.isPrimary(cartID) && !this.isReadOnly(cartID, term);
		},
		isDebug: function isDebug(cartID) {
			return cartID.indexOf(this.DEBUG_CART_PREFIX) === 0;
		},
		isPrimary: function isPrimary(cartID) {
			return cartID === this.PRIMARY_CART_ID ||
				cartID.indexOf(this.PRIMARY_CART_ID_PREFIX) === 0;
		},
		getPrimaryCartID: function getPrimaryCartID(term) {
			if (!sam.config.areCartsByCareer) {
				return this.PRIMARY_CART_ID;
			}

			const allCarts = this.all(term);
			if (allCarts.length < 1) {
				return this.PRIMARY_CART_ID;
			}

			return allCarts[0].id;
		},
		name: function name(cartID, term) {
			if (cartID === this.PRIMARY_CART_ID) {
				return sam.config.textPrimaryCart;
			}

			if (sam.config.areCartsByCareer) {
				const delimiter = cartID.indexOf(this.CART_CAREER_DELIMITER);
				if (delimiter !== -1) {
					let cartName = this.name(cartID.substr(0, delimiter), term);

					if (sam.user.termLevels(term).length > 1) {
						let level = cartID.substr(delimiter + 1);
						if (sam.config.levelCodeToName[level]) {
							level = sam.config.levelCodeToName[level];
						}
						cartName += ' - ' + level;
					}

					return cartName;
				}
			}

			return cartID;
		},
		gatherCarts: function gatherCarts(carts, term, type, options) {
			var context = { options: options, term: term, type: type };
			var mutable = { carts: carts.slice() };
			sam.events.s.emit(sam.cart.EVENT_GATHER_CARTS, context, mutable);
			return mutable.carts;
		},
		filterDuplicateCarts: function filterDuplicateCarts(a, index, carts) {
			for (var i = 0; i < carts.length; i++) {
				if (carts[i].id !== a.id) continue;
				if (carts[i].term !== a.term) continue;
				return i === index;
			}

			return false;
		},
		others: function others(options) {
			if (!options) {
				options = {skipDebug: false};
			}
			var carts = [];
			for (let term in termCarts) {
				const levels = sam.user.termLevels(term);
				for (let i = 0; i < termCarts[term].length; i++) {
					const cart = termCarts[term][i];
					if (options.skipDebug && this.isDebug(cart)) {
						continue;
					}

					if (sam.config.areCartsByCareer) {
						if (levels.length <= 1 && this.isPrimary(cart)) {
							continue;
						}
					} else if (this.isPrimary(cart)) {
						continue;
					}

					carts.push({
						id: cart,
						name: this.name(cart, term),
						term: term
					});
				}
			}

			if (sam.config.areCartsByCareer && sam.config.showEmptyCareerCarts) {
				if (!Array.isArray(foseConfig.srcDBs)) {
					foseConfig.srcDBs = [foseConfig.srcDBs];
				}
				var srcdbs = foseConfig.srcDBs.reduce(
					function (pv, cv) {
						if (!cv || cv.contains !== '') return pv;
						return pv.push(cv.code), pv;
					}, []
				)

				var self = this;
				srcdbs.forEach(function (term) {
					var levels = sam.user.termLevels(term);
					levels.forEach(function (level) {
						var cartID = self.PRIMARY_CART_ID_PREFIX + level
						carts.push({
							id: cartID,
							name: self.name(cartID, term),
							term: term
						})
					})
				})
			}

			carts = sam.cart.gatherCarts(carts, undefined, sam.cart.GATHER_TYPE_OTHERS, options);
			carts = carts.filter(sam.cart.filterDuplicateCarts);
			carts.sort(compareCarts);
			return carts;
		},
		all: function all(term, options) {
			if (!options) {
				options = {skipDebug: false};
			}
			var carts = [];

			carts.push({
				id: this.PRIMARY_CART_ID,
				name: this.name(this.PRIMARY_CART_ID, term),
				term: term
			});

			if (sam.config.areCartsByCareer) {
				const termLevels = sam.user.termLevels(term);
				for (let i = 0; i < termLevels.length; i++) {
					const level = termLevels[i];
					const id = this.PRIMARY_CART_ID_PREFIX + level;
					carts.push({
						id: id,
						name: this.name(id, term),
						term: term
					});
				}
			}

			if (termCarts[term]) {
				for (let i = 0; i < termCarts[term].length; i++) {
					const cart = termCarts[term][i];
					if (options.skipDebug && this.isDebug(cart)) {
						continue;
					}

					carts.push({
						id: cart,
						name: this.name(cart, term),
						term: term
					});
				}
			}

			if (sam.config.areCartsByCareer && carts.length > 1) {
				carts.shift();
			}

			carts = sam.cart.gatherCarts(carts, term, this.GATHER_TYPE_ALL, options)
			carts = carts.filter(sam.cart.filterDuplicateCarts);
			carts.sort(compareCarts);
			return carts;
		},
		allWriteable: function allWriteable(term) {
			const carts = [];

			const allCarts = this.all(term);
			for (let i = 0; i < allCarts.length; i++) {
				const cart = allCarts[i];
				if (!this.isReadOnly(cart.id, term)) {
					carts.push(cart);
				}
			}

			return carts;
		},
		containing: function containing(term, crn) {
			const carts = [];

			const allCarts = this.all(term);
			for (let i = 0; i < allCarts.length; i++) {
				const cart = allCarts[i];
				if (this.isInSpecific(cart.id, term, crn)) {
					carts.push(cart);
				}
			}

			return carts;
		},
		sectionToEnrollParams: function sectionToEnrollParams(cartID, term, cartEntry) {
			return Object.assign(
				sam.cart.cartEntryToAddParams( cartEntry ), {
				p_action: "cart_add",
				p_term_code: term,
				p_cart_name: cartID,
				p_reg_info: "E",
			});
		},
		cartEntryToAddParams: function cartEntryToAddParams(cartEntry) {
			return {
				p_crn: cartEntry.crn,
				p_hours: cartEntry.hours || "",
				p_gmod: cartEntry.gradeMode || "",
				p_meetinfo: cartEntry.meetInfo || "",
				p_add_path: cartEntry.addPath || "",
				p_prmsn_nbr: cartEntry.permissionNumber || "",
				p_crn_old: cartEntry.swapCrn || "",
				p_wait_list_okay: cartEntry.waitListOkay || "",
				p_crn_drop: cartEntry.dropCrn || "",
				p_reg_info: cartEntry.regInfo,
				p_options: cartEntry.options ? JSON.stringify(cartEntry.options) : cartEntry.optionsJSON,
			};
		},
		registeredToEnrollParams: function registeredToEnrollParams(cartID, term, regSection) {
			return {
				p_action: "cart_add",
				p_term_code: term,
				p_cart_name: cartID,
				p_crn: regSection.crn || "",
				p_hours: regSection.hours || "",
				p_gmod: regSection.gradeMode || "",
				p_reg_info: "E",
			}
		},

		rawCartKeys: {
			TERM: 0,
			CART: 1,
			CRN: 2,
			HOURS: 3,
			MEET_INFO: 4,
			RESOURCE_URL: 5,
			ADD_PATH: 6,
			COURSE: 7,
			EQUIVALENCIES: 8,
			GRADE_MODE: 9,
			ENROLL_CRN: 11,
			REG_INFO: 12,
			PERMISSION_NUMBER: 13,
			SWAP_CRN: 14,
			STATUS: 15,
			WAITLIST_OKAY: 16,
			DROP_CRN: 17,
			OPTIONS_JSON: 17, // Both DROP_CRN and OPTIONS_JSON use field 17
		},
		rawCartArray: function rawCartArray() {
			return "".split.call(Array(18), "|");
		}
	};

	exports.cache = new sam.cache.Cache();
	exports.cached = {
		read: exports.cache.withCacheAsync(exports.read, exports, {maxAge: 2500})
	};

	sam.events.on(sam.events.EVENT_GOT_CART, parseRawCart);
	sam.events.on(sam.events.EVENT_GOT_RECORD, parseRawCart);
	sam.events.on(sam.events.EVENT_LOGOUT, parseRawCart);

	function parseRawCartUsing(rawCart, mutable) {
		mutable.inAnyCart = {};
		mutable.inSpecificCart = {};
		mutable.cartContents = {};
		mutable.termCarts = {};

		var k = sam.cart.rawCartKeys;

		for (let i = 0; i < rawCart.length; i++) {
			const item = rawCart[i];
			const parts = item.split('|');
			const term = parts[k.TERM];
			const cart = parts[k.CART];
			const crn = parts[k.CRN];
			const hours = parts[k.HOURS];
			const meetInfo = parts[k.MEET_INFO];
			const resourceURL = parts[k.RESOURCE_URL];
			const addPath = parts[k.ADD_PATH];
			const course = parts[k.COURSE];
			const equivalencies = parts[k.EQUIVALENCIES].split(',');
			const gradeMode = parts[k.GRADE_MODE];
			const enrollCRN = parts[k.ENROLL_CRN];
			const regInfo = parts[k.REG_INFO];
			const permissionNumber = parts[k.PERMISSION_NUMBER];
			const swapCrn = parts[k.SWAP_CRN];
			const status = parts[k.STATUS];
			const waitListOkay = parts[k.WAITLIST_OKAY];
			const dropCrn = parts[k.DROP_CRN];
			const optionsJSON = parts[k.OPTIONS_JSON];

			mutable.inAnyCart[term + '|' + crn] = true;
			mutable.inSpecificCart[term + '|' + cart+ '|' + crn] = true;

			if (!mutable.termCarts[term]) {
				mutable.termCarts[term] = [];
			}

			if (mutable.termCarts[term].indexOf(cart) === -1) {
				mutable.termCarts[term].push(cart);
			}

			const cartID = term + '|' + cart;
			if (!mutable.cartContents[cartID]) {
				mutable.cartContents[cartID] = [];
			}
			var options = {};
			try {
				options = JSON.parse(optionsJSON);
			} catch (ex) {
				options = {};
			}
			mutable.cartContents[cartID].push({
				crn: crn,
				hours: hours,
				meetInfo: meetInfo,
				resourceURL: resourceURL,
				addPath: addPath,
				course: course,
				equivalencies: equivalencies,
				gradeMode: gradeMode,
				enrollCRN: enrollCRN,
				regInfo: regInfo,
				permissionNumber: permissionNumber,
				swapCrn: swapCrn,
				status: status,
				waitListOkay: waitListOkay,
				dropCrn: dropCrn,
				optionsJSON: optionsJSON,
				options: options,
				acadCareer: options.level || ""
			});
		}
	}
	function parseRawCart() {
		const rawCart = sam.user.getProperty('cart') || [];
		exports.cache.set({cart: sam.user.getProperty('cart') || []}, exports.read, exports);

		var mutable = {};
		parseRawCartUsing(rawCart, mutable);
		inAnyCart = mutable.inAnyCart;
		inSpecificCart = mutable.inSpecificCart;
		cartContents = mutable.cartContents;
		termCarts = mutable.termCarts;

		const readOnlyCarts = sam.user.getProperty('readonlycarts') || [];
		readCarts = {};
		for (let i = 0; i < readOnlyCarts.length; i++) {
			const item = readOnlyCarts[i];
			readCarts[item] = true;
		}

		return Promise.resolve();
	}

	exports.parse = parseRawCart
	exports.parseUsing = parseRawCartUsing;
	function compareCarts(a, b) {
		const aIsPrimary = sam.cart.isPrimary(a.id);
		const bIsPrimary = sam.cart.isPrimary(b.id);
		if (aIsPrimary && bIsPrimary) {
			return a.name.localeCompare(b.name);
		}

		if (aIsPrimary) {
			return -1;
		}

		return 1;
	}

	return exports;
}();


sam.plan = function () {
	'use strict';

	let apiTimeout = 30000;

	sam.config.textPrimaryPlan = sam.config.textPrimaryPlan || sam.config.textPrimaryCart || 'Primary';

	const exports = {
		PRIMARY_PLAN_ID: 'default',
		SNAPSHOT_PREFIX: 'Snapshot: ',
	};

	exports.all = function() { //
		return Object.entries( sam.user.allPlans() ).map( function(kv) {
			return { id: kv[0], name: sam.plan.planName(kv[0]), isSnapshot: kv[1].isSnapshot };
		});
	};

	exports.planName = function( planId ) {
		return sam.plan.PRIMARY_PLAN_ID == planId ? sam.config.textPrimaryPlan : planId;
	};

	exports.containing = function containing( courseCode ) {
		return sam.plan.all().filter( function(plan) {
			return sam.plan.contents( plan.id ).some( function(it) {
				return it.code == courseCode;
			});
		});
	};

	exports.contents = function contents( planId ) {
		var plan = sam.user.allPlans()[ planId ] || {};
		var entries = (plan.entries || []).slice();
		var termsOrder = { '': 1 }; // term-less on top, non-zero values
		exports.terms().forEach( function(t,i) { termsOrder[t.code] = 2+i; } );
		entries.forEach( function(x,i) { termsOrder[ x.term ] = termsOrder[ x.term ] || 100000+i; } );
		entries.sort( function(a,b) { return termsOrder[ a.term ] - termsOrder[ b.term ]; } );
		return entries.map( function(x) {
			return Object.assign( { code: x.courseCode }, x );
		});
	};

	exports.request = function request( parameters, context ) {
		let url = sam.url.addParameters( sam.config.cartURL, parameters );
		const apiTimeout = 60000; //SAM_API_TIMEOUT;
		return Promise.resolve({
		}).then( function() {
			return sam.fetch.jsonCompat( url, 'setPlan', apiTimeout );
		}).then( function( response ) {
			console.log({ plans_response: response });
			if ( response.error ) {
				throw new Error( response.error );
			}
			sam.user.updatePlansFromRawRecord( response );
			return response;
		});
	};

	exports.addCourse = function( args ) { // planId, courseCode, termCode [, surrogateId, courseTitle]
		var codeParts = args.courseCode.split(' ');
		const params = {
			action: 'plan_add',
			plan_name: args.planId,
			subj: codeParts[ 0 ],
			crse: codeParts.slice(1).join(' '),
			term_code: args.termCode,
			surrogate_id: args.surrogateId || undefined,
		};
		const context = {
			source: 'plan-add',
		};
		return sam.plan.request( params, context );
	};

	exports.removeCourse = function( args ) { // planId, courseCode
		const params = {
			action: 'plan_remove',
			surrogate_id: args.surrogateId,
		};
		const context = {
			source: 'plan-remove',
		};
		return sam.plan.request( params, context );
	};

	exports.createSnapshot = function( args ) { // srcPlanId, snapshotName
		const params = {
			action: 'plan_copy',
			copy_from: args.srcPlanId,
			copy_to: sam.plan.SNAPSHOT_PREFIX + args.snapshotName,
		};
		const context = {
			source: 'plan-create-snapshot',
		};
		return sam.plan.request( params, context );
	};

	return exports;

	exports.addCourse = function( args ) { // planId, courseCode, termCode [, courseTitle]
		const params = {
			p_action: 'cart_add',
			p_cart_name: makeCartId( args.planId, args.termCode ),
			p_term_code: TERM_PLANS,
			p_crn: args.courseCode,
		};
		const context = {
			source: 'plan-add',
		};
		return sam.plan.request( params, context );
	};

	exports.removeCourse = function( args ) { // planId, courseCode
		var foundInPlan = sam.plan.contents( args.planId ).filter( function(it) {
			return it.code == args.courseCode;
		})[ 0 ];
		if ( !foundInPlan ) {
			return Promise.resolve();
		}
		const params = {
			p_action: 'cart_remove',
			p_cart_name: makeCartId( args.planId, foundInPlan.term ),
			p_term_code: TERM_PLANS,
			p_crn: foundInPlan.code,
		};
		const context = {
			source: 'plan-remove',
		};
		return sam.cart.request( params, context );
	};

	return exports;
}();


sam.storage = function () {
	'use strict';

	const exports = {}

	var ephemeralStorage = {};
	exports.ephemeral = function ephemeral() {
		return ephemeralStorage;
	}

	function clearEphemeralStorage() {
		ephemeralStorage = {};
		return Promise.resolve();
	}

	sam.events.on(sam.events.EVENT_LOGOUT, clearEphemeralStorage);

	return exports;
}();


if (typeof window.require === 'undefined') {
	window.require = function require(moduleId) {
		if (require.installed[moduleId]) {
			return require.installed[moduleId].exports;
		}

		if (!require.modules[moduleId]) {
			throw new Error('Could not load module "' + moduleId + '"');
		}

		let module = {
			exports: {},
			id: moduleId,
			loaded: false
		};

		require.installed[moduleId] = module;
		require.modules[moduleId].call(
			module.exports,
			module,
			module.exports,
			window,
			require
		);

		module.loaded = true;

		return module.exports;
	}

	window.require.modules = {};
	window.require.installed = {};
	window._lfreq_ = window.require;
}

window.require.installed['sam/url'] = {
	id: 'sam/url',
	loaded: true,
	exports: sam.url
};

window.require.installed['sam/jsonp'] = {
	id: 'sam/jsonp',
	loaded: true,
	exports: {
		fetch: sam.fetch.jsonCompat
	}
};

sam.dialog.setTemplate('\x3cdiv class=\x22{{id}}__head {%+ if busy %}{{id}}__head--busy{% endif %}\x22>\x0A\x09{{config.textHead|default(\x27Authentication\x27)}}\x0A\x09\x3cbutton class=\x22fa fa-times {{id}}__close\x22 type=\x22button\x22>\x0A\x09\x09\x3cspan class=\x22sr-only\x22>{{config.textClose|default(\x27Close\x27)}}\x3c/span>\x0A\x09\x3c/button>\x0A\x3c/div>\x0A\x3cdiv class=\x22{{id}}__body\x22>\x0A\x09\x3cp class=\x22{{id}}__message\x22>{{message}}\x3c/p>\x0A\x09{% if error %}\x0A\x09\x3cdiv class=\x22{{id}}__error\x22>{{error}}\x3c/div>\x0A\x09{% endif %}\x0A\x3c/div>\x0A\x3cdiv class=\x22{{id}}__foot\x22>\x0A\x09\x3cbutton class=\x22{{id}}__button {{id}}__button--cancel\x22>{{config.textCancel|default(\x27Cancel\x27)}}\x3c/button>\x0A\x09\x3cbutton class=\x22{{id}}__button {{id}}__button--login\x22>{{config.textLogin|default(\x27Login\x27)}}\x3c/button>\x0A\x3c/div>\x0A');
sam.config.majorCodeToName = {"AMPH - MPH":{"title":"Accelerated Master of Public Health - MPH","href":"/graduate/concentrations/amph/index.html"},"BIOS-SCM-HDS":{"title":"Biostatistics - SCM (Health Data Science)","href":"/graduate/concentrations/bios/index.html"},"BIOS-AM":{"title":"Biostatistics - AM","href":"/graduate/concentrations/bios/index.html"},"BIOS-PHD":{"title":"Biostatistics - PHD","href":"/graduate/concentrations/bios/index.html"},"BIOS-SCM":{"title":"Biostatistics - SCM","href":"/graduate/concentrations/bios/index.html"},"BIOT-PHD":{"title":"Biotechnology - PHD","href":"/graduate/concentrations/biot/index.html"},"BIOT-SCM":{"title":"Biotechnology - SCM","href":"/graduate/concentrations/biot/index.html"},"BIOT-AM":{"title":"Biotechnology - AM","href":"/graduate/concentrations/biot/index.html"},"BSHS-PHD":{"title":"Behavioral &amp; Social Health Sci - PHD","href":"/graduate/concentrations/bshs/index.html"},"CEDS-SCM":{"title":"Data-Enabled Computational Engineering and Science - SCM","href":"/graduate/concentrations/ceds/index.html"},"CHEG-SCM-TH":{"title":"Chemical Engineering Thesis - SCM","href":"/graduate/concentrations/cheg/index.html"},"CLTR-SCM":{"title":"Clinical &amp; Translational Research - SCM","href":"/graduate/concentrations/cltr/index.html"},"CLTR-GR CRT":{"title":"Clinical &amp; Translational Research - GR CRT","href":"/graduate/concentrations/cltr/index.html"},"CLTR-CRT":{"title":"Clinical &amp; Translational Rsch","href":"/graduate/concentrations/cltr/index.html"},"COMP-SCM":{"title":"Computer Science - SCM","href":"/graduate/concentrations/comp/index.html"},"CYBR-SCM-COMP":{"title":"Cybersecurity - SCM (Computer Science)","href":"/graduate/concentrations/cybr/index.html"},"CYBR-SCM-PLCY":{"title":"Cybersecurity - SCM (Policy)","href":"/graduate/concentrations/cybr/index.html"},"CYBS-SCM-COMP":{"title":"Cybersecurity - SCM (Computer Science)","href":"/graduate/concentrations/cybs/index.html"},"CYBS-SCM-PLCY":{"title":"Cybersecurity - SCM (Policy)","href":"/graduate/concentrations/cybs/index.html"},"DATA-SCM":{"title":"Data Science - SCM","href":"/graduate/concentrations/data/index.html"},"DESE-AM":{"title":"Design Engineering - AM","href":"/graduate/concentrations/dese/index.html"},"DPGS-SCM":{"title":"Data Science Policy, Governance &amp; Society - SCM","href":"/graduate/concentrations/dpgs/index.html"},"ECEG-SCM-TH":{"title":"Electrical and Computer Engineering Thesis - SCM","href":"/graduate/concentrations/eceg/index.html"},"ENGL-MAT":{"title":"English - MAT","href":"/graduate/concentrations/educ/index.html"},"SSTU-MAT":{"title":"Social Studies - MAT","href":"/graduate/concentrations/educ/index.html"},"SCIE-MAT":{"title":"Science - MAT","href":"/graduate/concentrations/educ/index.html"},"MATH-MAT":{"title":"Mathematics - MAT","href":"/graduate/concentrations/educ/index.html"},"URBE-AM":{"title":"Urban Education Policy - AM","href":"/graduate/concentrations/educ/index.html"},"BUSI-EMBA":{"title":"Business Administration - EMBA","href":"/graduate/concentrations/emba/index.html"},"ENBI-SCM":{"title":"Biomedical Engineering - SCM","href":"/graduate/concentrations/enbi/index.html"},"ENBM-MENG":{"title":"Biomedical Engineering - MENG","href":"/graduate/concentrations/enbm/index.html"},"EPID-PHD":{"title":"Epidemiology - PHD","href":"/graduate/concentrations/epid/index.html"},"EVEG-SCM-TH":{"title":"Environmental Engineering Thesis - SCM","href":"/graduate/concentrations/eveg/index.html"},"GPHP-MPH":{"title":"Public Health (Generalist) - MPH","href":"/graduate/concentrations/gphp/index.html"},"HCL-SCM":{"title":"Health Care Leadership - SCM","href":"/graduate/concentrations/hcl/index.html"},"HINF-SCM":{"title":"Health Informatics and Artificial Intelligence - SCM","href":"/graduate/concentrations/hinf/index.html"},"HIST-AM":{"title":"History - AM","href":"/graduate/concentrations/hist/index.html"},"MEAM-SCM-TH":{"title":"Mechanical Engineering and Applied Mechanics Thesis - SCM","href":"/graduate/concentrations/meam/index.html"},"MEDI-SCM":{"title":"Medical Science - SCM","href":"/graduate/concentrations/medi/index.html"},"MGMT-MIM-OL":{"title":"Master in Management","href":"/graduate/concentrations/mgmt/index.html"},"MIME-SCM":{"title":"Program in Innovation Management and Entrepreneurship - SCM","href":"/graduate/concentrations/mime/index.html"},"MPHY-SCM":{"title":"Medical Physics - SCM","href":"/graduate/concentrations/mphy/index.html"},"MTEG-SCM-TH":{"title":"Materials Science and Engineering Thesis - SCM","href":"/graduate/concentrations/mteg/index.html"},"ORGL-SCM":{"title":"Organizational Leadership - SCM","href":"/graduate/concentrations/orgl/index.html"},"PHYS-SCM":{"title":"Physics - SCM","href":"/graduate/concentrations/phys/index.html"},"PBED-AM":{"title":"ESL and Cross-Cultural Studies - AM","href":"/graduate/concentrations/pobs/index.html"},"PUBA-MPA":{"title":"Public Affairs - MPA","href":"/graduate/concentrations/ppol/index.html"},"PUBA-MPA-DPLA":{"title":"Public Affairs - MPA (Data and Policy Analysis)","href":"/graduate/concentrations/ppol/index.html"},"PUBA-MPA-IPP":{"title":"Public Affairs - MPA (Inequity and Public Policy)","href":"/graduate/concentrations/ppol/index.html"},"PUBA-MPA-GLSC":{"title":"Public Affairs - MPA (Global Security)","href":"/graduate/concentrations/ppol/index.html"},"PUBA-MPA-PLMG":{"title":"Public Affairs - MPA (Public Leadership and Mgmt.)","href":"/graduate/concentrations/ppol/index.html"},"PUBH-MPH":{"title":"Public Health - MPH","href":"/graduate/concentrations/pubh/index.html"},"RELS-AM":{"title":"Religious Studies - AM","href":"/graduate/concentrations/rels/index.html"},"SDA-SCM":{"title":"Social Data Analytics - SCM","href":"/graduate/concentrations/sda/index.html"},"SUST-SCM":{"title":"Sustainable Energy - SCM","href":"/graduate/concentrations/sust/index.html"},"TECL-SCM":{"title":"Technology Leadership - SCM","href":"/graduate/concentrations/tecl/index.html"},"THST-MFA":{"title":"Theatre &amp; Performance Studies - MFA","href":"/graduate/concentrations/thta/index.html"},"PLYW-MFA":{"title":"Theatre Arts &amp; Performance Studies: Playwriting - MFA","href":"/graduate/concentrations/thta/index.html"},"ACTG-MFA":{"title":"Theatre Arts &amp; Performance Studies: Acting (MFA) - MFA","href":"/graduate/concentrations/thta/index.html"},"DRTG-MFA":{"title":"Theatre Arts &amp; Performance Studies: Directing (MFA) - MFA","href":"/graduate/concentrations/thta/index.html"},"AFRI-AB":{"title":"Africana Studies - AB","href":"/the-college/concentrations/afri/index.html"},"AMST-AB":{"title":"American Studies - AB","href":"/the-college/concentrations/amst/index.html"},"ANTH-AB":{"title":"Anthropology - AB","href":"/the-college/concentrations/anth/index.html"},"ANTH-AB-ANTG":{"title":"Anthropology - AB (General Anthropology)","href":"/the-college/concentrations/anth/index.html"},"ANTH-AB-ANTM":{"title":"Anthropology - AB (Medical Anthropology)","href":"/the-college/concentrations/anth/index.html"},"ANTH-AB-ANTS":{"title":"Anthropology - AB (Socio-cultural Anthropology)","href":"/the-college/concentrations/anth/index.html"},"ANTH-AB-LANT":{"title":"Anthropology - AB (Linguistic Anthropology)","href":"/the-college/concentrations/anth/index.html"},"ANTH-AB-ANTA":{"title":"Anthropology - AB (Anthropological Archaeology)","href":"/the-college/concentrations/anth/index.html"},"ANTH-AB-ANTB":{"title":"Anthropology - AB (Biological Anthropology)","href":"/the-college/concentrations/anth/index.html"},"APMA-AB":{"title":"Applied Mathematics - AB","href":"/the-college/concentrations/apma/index.html"},"APMA-SCB":{"title":"Applied Mathematics - SCB","href":"/the-college/concentrations/apma/index.html"},"APMB-SCB":{"title":"Applied Mathematics-Biology - SCB","href":"/the-college/concentrations/apmb/index.html"},"APMC-SCB":{"title":"Applied Mathematics-Computer Science - SCB","href":"/the-college/concentrations/apmc/index.html"},"APMC-SCB-PROF":{"title":"Applied Math.-Computer Sci. - SCB (Professional Track)","href":"/the-college/concentrations/apmc/index.html"},"APME-AB":{"title":"Applied Mathematics-Economics - AB (No concentration)","href":"/the-college/concentrations/apme/index.html"},"APME-AB-ADEC":{"title":"Applied Mathematics-Economics - AB (Advanced Economics)","href":"/the-college/concentrations/apme/index.html"},"APME-AB-AEPF":{"title":"Applied Mathematics-Economics - AB (Advanced Economics-Prof.)","href":"/the-college/concentrations/apme/index.html"},"APME-AB-MAFI":{"title":"Applied Mathematics-Economics - AB (Mathematical Finance)","href":"/the-college/concentrations/apme/index.html"},"APME-AB-MFPF":{"title":"Applied Mathematics-Economics - AB (Mathematical Finance-Prof.)","href":"/the-college/concentrations/apme/index.html"},"APME-SCB":{"title":"Applied Mathematics-Economics - SCB (No concentration)","href":"/the-college/concentrations/apme/index.html"},"APME-SCB-ADEC":{"title":"Applied Mathematics-Economics - SCB (Advanced Economics)","href":"/the-college/concentrations/apme/index.html"},"APME-SCB-AEPF":{"title":"Applied Mathematics-Economics - SCB (Advanced Economics-Prof.)","href":"/the-college/concentrations/apme/index.html"},"APME-SCB-MAFI":{"title":"Applied Mathematics-Economics - SCB (Mathematical Finance)","href":"/the-college/concentrations/apme/index.html"},"APME-SCB-MFPF":{"title":"Applied Mathematics-Economics - SCB (Mathematical Finance-Prof.)","href":"/the-college/concentrations/apme/index.html"},"ARAN-AB":{"title":"Archaeology &amp; Ancient World - AB","href":"/the-college/concentrations/aran/index.html"},"ARAN-AB-CLSS":{"title":"Archeology &amp; Ancient World - AB (Classical)","href":"/the-college/concentrations/aran/index.html"},"ARAN-AB-EGAS":{"title":"Archeology &amp; Ancient World - AB (Egyptology and Anct W. Asia St)","href":"/the-college/concentrations/aran/index.html"},"ARCT-AB":{"title":"Architecture - AB","href":"/the-college/concentrations/arct/index.html"},"ASTR-AB":{"title":"Astronomy - AB","href":"/the-college/concentrations/astr/index.html"},"BCHM-SCB":{"title":"Biochemistry &amp; Molecular Biology - SCB","href":"/the-college/concentrations/bchm/index.html"},"BDS-AB":{"title":"Behavioral Decision Sciences - AB","href":"/the-college/concentrations/bds/index.html"},"BIOL-AB":{"title":"Biology - AB","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB":{"title":"Biology - SCB","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-CEMB":{"title":"Biology - SCB (Cell and Molecular Biology)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-EBIO":{"title":"Biology - SCB (Ecology, Evolutionary Biology)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-IMMU":{"title":"Biology - SCB (Immunobiology)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-MAR":{"title":"Biology - SCB (Marine Biology)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-NBIO":{"title":"Biology - SCB (Neurobiology)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-PHBI":{"title":"Biology - SCB (Physiology/Biotechnology)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-PHSC":{"title":"Biology - SCB (Physical Sciences)","href":"/the-college/concentrations/biol/index.html"},"BIOL-SCB-BINF":{"title":"Biology - SCB (Biomedical Informatics)","href":"/the-college/concentrations/biol/index.html"},"BIOP-SCB":{"title":"Biophysics - SCB","href":"/the-college/concentrations/biop/index.html"},"CHEG-SCB":{"title":"Chemical Engineering - SCB","href":"/the-college/concentrations/cheg/index.html"},"CHEG-SCB-PROF":{"title":"Chemical Engineering - SCB (Professional Track)","href":"/the-college/concentrations/cheg/index.html"},"CHEM-AB":{"title":"Chemistry - AB","href":"/the-college/concentrations/chem/index.html"},"CHEM-SCB":{"title":"Chemistry - SCB","href":"/the-college/concentrations/chem/index.html"},"CHEM-SCB-CHBI":{"title":"Chemistry - SCB (Chemical Biology)","href":"/the-college/concentrations/chem/index.html"},"CHEM-SCB-MATL":{"title":"Chemistry - SCB (Materials)","href":"/the-college/concentrations/chem/index.html"},"CHPH-SCB":{"title":"Chemical Physics - SCB","href":"/the-college/concentrations/chph/index.html"},"CLAS-AB":{"title":"Classics - AB","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-GRKK":{"title":"Classics - AB (Greek)","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-LTIN":{"title":"Classics - AB (Latin)","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-GKLN":{"title":"Classics - AB (Greek and Latin)","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-SACL":{"title":"Classics - AB (South Asian Classics)","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-SANS":{"title":"Classics - AB (Sanskrit)","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-GRSA":{"title":"Classics - AB (Greek and Sanskrit)","href":"/the-college/concentrations/clas/index.html"},"CLAS-AB-LTSA":{"title":"Classics - AB (Latin and Sanskrit)","href":"/the-college/concentrations/clas/index.html"},"CNEU-SCB":{"title":"Computational Neuroscience - SCB","href":"/the-college/concentrations/cneu/index.html"},"COEG-SCB-PROF":{"title":"Computer Engineering - SCB (Professional Track)","href":"/the-college/concentrations/coeg/index.html"},"COEG-SCB":{"title":"Computer Engineering - SCB","href":"/the-college/concentrations/coeg/index.html"},"COGN-SCB":{"title":"Cognitive Neuroscience - SCB","href":"/the-college/concentrations/cogn/index.html"},"COGN-AB":{"title":"Cognitive Neuroscience - AB","href":"/the-college/concentrations/cogn/index.html"},"COGS-AB":{"title":"Cognitive Science - AB","href":"/the-college/concentrations/cogs/index.html"},"COGS-SCB":{"title":"Cognitive Science - SCB","href":"/the-college/concentrations/cogs/index.html"},"COLT-AB":{"title":"Comparative Literature - AB","href":"/the-college/concentrations/colt/index.html"},"COLT-AB-LITB":{"title":"Comparative Literature - AB (Literature in Two Languages)","href":"/the-college/concentrations/colt/index.html"},"COLT-AB-LITC":{"title":"Comparative Literature - AB (Literature in Three Languages)","href":"/the-college/concentrations/colt/index.html"},"COLT-AB-LTRN":{"title":"Comparative Literature - AB (Literary Translation)","href":"/the-college/concentrations/colt/index.html"},"COMP-AB":{"title":"Computer Science - AB","href":"/the-college/concentrations/comp/index.html"},"COMP-AB-PROF":{"title":"Computer Science - AB (Professional Track)","href":"/the-college/concentrations/comp/index.html"},"COMP-SCB":{"title":"Computer Science - SCB","href":"/the-college/concentrations/comp/index.html"},"COMP-SCB-PROF":{"title":"Computer Science - SCB (Professional Track)","href":"/the-college/concentrations/comp/index.html"},"CSBI-SCB":{"title":"Computational Biology - SCB","href":"/the-college/concentrations/csbi/index.html"},"CSBI-SCB-AMSG":{"title":"Computational Biology - SCB (Applied Math &amp; Statistics)","href":"/the-college/concentrations/csbi/index.html"},"CSBI-SCB-BISC":{"title":"Computational Biology - SCB (Biological Sciences)","href":"/the-college/concentrations/csbi/index.html"},"CSBI-SCB-CGEN":{"title":"Computational Biology - SCB (Computer Science)","href":"/the-college/concentrations/csbi/index.html"},"CSBI-AB":{"title":"Computational Biology - AB","href":"/the-college/concentrations/csbi/index.html"},"CSEC-AB":{"title":"Computer Science-Economics - AB","href":"/the-college/concentrations/csec/index.html"},"CSEC-AB-PROF":{"title":"Computer Science-Economics - AB (Professional Track)","href":"/the-college/concentrations/csec/index.html"},"CSEC-SCB":{"title":"Computer Science-Economics - SCB","href":"/the-college/concentrations/csec/index.html"},"CSEC-SCB-PROF":{"title":"Computer Science-Economics - SCB (Professional Track)","href":"/the-college/concentrations/csec/index.html"},"CTMP-AB":{"title":"Contemplative Studies - AB","href":"/the-college/concentrations/ctmp/index.html"},"CTMP-AB-HUMN":{"title":"Contemplative Studies - AB (Humanities)","href":"/the-college/concentrations/ctmp/index.html"},"CTMP-AB-SCI":{"title":"Contemplative Studies - AB (Sciences)","href":"/the-college/concentrations/ctmp/index.html"},"DESE-SCB":{"title":"Design Engineering - SCB","href":"/the-college/concentrations/dese/index.html"},"EAST-AB":{"title":"East Asian Studies - AB","href":"/the-college/concentrations/east/index.html"},"ECB-AB":{"title":"Earth, Climate, and Biology - AB","href":"/the-college/concentrations/ecb/index.html"},"ECB-SCB":{"title":"Earth, Climate, and Biology - SCB","href":"/the-college/concentrations/ecb/index.html"},"ECON-AB":{"title":"Economics - AB","href":"/the-college/concentrations/econ/index.html"},"ECON-AB-PROF":{"title":"Economics - AB (Professional Track)","href":"/the-college/concentrations/econ/index.html"},"ECON-AB-BSEC":{"title":"Economics - AB (Business Economics)","href":"/the-college/concentrations/econ/index.html"},"ECON-AB-BSEP":{"title":"Economics - AB (Business Econ Professional Track)","href":"/the-college/concentrations/econ/index.html"},"ECON-AB-PPLC":{"title":"Economics - AB (Public Policy)","href":"/the-college/concentrations/econ/index.html"},"ECON-AB-PPLP":{"title":"Economics - (Public Policy Professional Track)","href":"/the-college/concentrations/econ/index.html"},"EDUC-AB":{"title":"Education Studies - AB","href":"/the-college/concentrations/educ/index.html"},"EDUC-AB-HIPO":{"title":"Education Studies - AB (History and Policy)","href":"/the-college/concentrations/educ/index.html"},"EDUC-AB-HUDV":{"title":"Education Studies - AB (Human Development)","href":"/the-college/concentrations/educ/index.html"},"EGYA-AB":{"title":"Egyptology &amp; Assyriology - AB (No concentration)","href":"/the-college/concentrations/egya/index.html"},"EGYA-AB-ASYR":{"title":"Egyptology &amp; Assyriology - AB (Assyriology)","href":"/the-college/concentrations/egya/index.html"},"EGYA-AB-EGYT":{"title":"Egyptology &amp; Assyriology - AB (Egyptology)","href":"/the-college/concentrations/egya/index.html"},"ELEG-SCB-PROF":{"title":"Electrical Engineering - SCB (Professional Track)","href":"/the-college/concentrations/eleg/index.html"},"ELEG-SCB":{"title":"Electrical Engineering - SCB","href":"/the-college/concentrations/eleg/index.html"},"EMOW-AB":{"title":"Early Modern World - AB","href":"/the-college/concentrations/emow/index.html"},"ENBI-SCB":{"title":"Biomedical Engineering - SCB","href":"/the-college/concentrations/enbi/index.html"},"ENGL-AB":{"title":"English - AB","href":"/the-college/concentrations/engl/index.html"},"ENPH-SCB":{"title":"Engineering and Physics - SCB","href":"/the-college/concentrations/enph/index.html"},"ENVS-AB":{"title":"Environmental Sciences and Studies - AB","href":"/the-college/concentrations/envs/index.html"},"ENVS-SCB":{"title":"Environmental Sciences and Studies - SCB","href":"/the-college/concentrations/envs/index.html"},"ENVS-SCB-CLE":{"title":"Environmental Sciences and Studies - SCB (Climate and Energy)","href":"/the-college/concentrations/envs/index.html"},"ENVS-SCB-CSN":{"title":"Environmental Sciences and Studies - SCB (Conservation Science and Natural Systems)","href":"/the-college/concentrations/envs/index.html"},"ENVS-SCB-EJH":{"title":"Environmental Sciences and Studies - SCB (Environmental Justice and Health)","href":"/the-college/concentrations/envs/index.html"},"ENVS-SCB-SDG":{"title":"Environmental Sciences and Studies - SCB (Sustainable Development and Governance)","href":"/the-college/concentrations/envs/index.html"},"EPS-AB":{"title":"Earth and Planetary Science - AB","href":"/the-college/concentrations/eps/index.html"},"EPS-SCB":{"title":"Earth and Planetary Science - SCB","href":"/the-college/concentrations/eps/index.html"},"ETHS-AB":{"title":"Ethnic Studies - AB","href":"/the-college/concentrations/eths/index.html"},"EVEG-SCB":{"title":"Environmental Engineering - SCB","href":"/the-college/concentrations/eveg/index.html"},"EVEG-SCB-PROF":{"title":"Environmental Engineering - SCB (Professional Track)","href":"/the-college/concentrations/eveg/index.html"},"FFS-AB":{"title":"French &amp; Francophone Studies - AB","href":"/the-college/concentrations/ffs/index.html"},"GCEC-AB":{"title":"Geochemistry and Environmental Chemistry - AB","href":"/the-college/concentrations/gcec/index.html"},"GCEC-SCB":{"title":"Geochemistry and Environmental Chemistry - SCB","href":"/the-college/concentrations/gcec/index.html"},"GMST-AB":{"title":"German Studies - AB","href":"/the-college/concentrations/gmst/index.html"},"GNSS-AB":{"title":"Gender &amp; Sexuality Studies - AB","href":"/the-college/concentrations/gnss/index.html"},"GPCP-AB":{"title":"Geophysics and Climate Physics - AB","href":"/the-college/concentrations/gpcp/index.html"},"GPCP-SCB":{"title":"Geophysics and Climate Physics - SCB","href":"/the-college/concentrations/gpcp/index.html"},"HHBI-AB":{"title":"Health and Human Biology - AB","href":"/the-college/concentrations/hhbi/index.html"},"HIAA-AB":{"title":"History of Art and Architecture - AB","href":"/the-college/concentrations/hiaa/index.html"},"HIST-AB":{"title":"History - AB","href":"/the-college/concentrations/hist/index.html"},"HSLC-AB":{"title":"Hispanic Literatures and Cultures - AB","href":"/the-college/concentrations/hslc/index.html"},"IAPA-AB":{"title":"International and Public Affairs - AB","href":"/the-college/concentrations/iapa/index.html"},"IAPA-AB-DEV":{"title":"International and Public Affairs - AB (Development)","href":"/the-college/concentrations/iapa/index.html"},"IAPA-AB-SEC":{"title":"International and Public Affairs - AB (Security)","href":"/the-college/concentrations/iapa/index.html"},"IAPA-AB-POL":{"title":"International and Public Affairs - AB (Policy and Governance)","href":"/the-college/concentrations/iapa/index.html"},"INDP-AB":{"title":"Independent Concentration - AB","href":"/the-college/concentrations/indp/index.html"},"INDP-AB-STAT":{"title":"Independent Concentration - AB (Statistics)","href":"/the-college/concentrations/indp/index.html"},"INDP-SCB":{"title":"Independent Concentration - SCB","href":"/the-college/concentrations/indp/index.html"},"INDP-SCB-STAT":{"title":"Independent Concentration - SCB (Statistics)","href":"/the-college/concentrations/indp/index.html"},"ITAL-AB":{"title":"Italian Studies - AB","href":"/the-college/concentrations/ital/index.html"},"JUDS-AB":{"title":"Judaic Studies - AB","href":"/the-college/concentrations/juds/index.html"},"LACS-AB":{"title":"Latin American &amp; Caribbean Studies - AB","href":"/the-college/concentrations/lacs/index.html"},"LING-AB":{"title":"Linguistics - AB","href":"/the-college/concentrations/ling/index.html"},"LING-SCB":{"title":"Linguistics - SCB","href":"/the-college/concentrations/ling/index.html"},"LITA-AB":{"title":"Literary Arts - AB","href":"/the-college/concentrations/lita/index.html"},"MACS-SCB":{"title":"Mathematics-Computer Science - SCB","href":"/the-college/concentrations/macs/index.html"},"MAEG-SCB":{"title":"Materials Engineering - SCB","href":"/the-college/concentrations/maeg/index.html"},"MAEG-SCB-PROF":{"title":"Materials Engineering - SCB (Professional Track)","href":"/the-college/concentrations/maeg/index.html"},"MATH-AB":{"title":"Mathematics - AB","href":"/the-college/concentrations/math/index.html"},"MATH-SCB":{"title":"Mathematics - SCB","href":"/the-college/concentrations/math/index.html"},"MCEG-SCB":{"title":"Mechanical Engineering - SCB","href":"/the-college/concentrations/mceg/index.html"},"MCEG-SCB-PROF":{"title":"Mechanical Engineering - SCB (Professional Track)","href":"/the-college/concentrations/mceg/index.html"},"MCMD-AB":{"title":"Modern Culture and Media - AB (No concentration)","href":"/the-college/concentrations/mcmd/index.html"},"MCMD-AB-TRK1":{"title":"Modern Culture and Media - AB (Track I)","href":"/the-college/concentrations/mcmd/index.html"},"MCMD-AB-TRK2":{"title":"Modern Culture and Media - AB (Track II)","href":"/the-college/concentrations/mcmd/index.html"},"MCMD-AB-THEO":{"title":"Modern Culture and Media - AB (Theory based)","href":"/the-college/concentrations/mcmd/index.html"},"MCMD-AB-PRAC":{"title":"Modern Culture and Media - AB (Practice based)","href":"/the-college/concentrations/mcmd/index.html"},"MDVC-AB":{"title":"Medieval Cultures - AB ","href":"/the-college/concentrations/mdvc/index.html"},"MDVC-AB-ANTQ":{"title":"Medieval Cultures - AB (Late Antique Cultures)","href":"/the-college/concentrations/mdvc/index.html"},"MIDE-AB":{"title":"Middle Eastern Studies - AB","href":"/the-college/concentrations/mide/index.html"},"MTEC-AB":{"title":"Mathematics-Economics - AB","href":"/the-college/concentrations/mtec/index.html"},"MUSC-AB":{"title":"Music - AB","href":"/the-college/concentrations/musc/index.html"},"NAIS-AB":{"title":"Critical Native American and Indigenous Studies - AB","href":"/the-college/concentrations/nais/index.html"},"NEUR-SCB":{"title":"Neuroscience - SCB","href":"/the-college/concentrations/neur/index.html"},"PHIL-AB":{"title":"Philosophy - AB","href":"/the-college/concentrations/phil/index.html"},"PHIL-AB-ETPP":{"title":"Philosophy - AB (Ethics &amp; Political Philosophy)","href":"/the-college/concentrations/phil/index.html"},"PHIL-AB-LOGC":{"title":"Philosophy - AB (Logic &amp; Philosophy of Science)","href":"/the-college/concentrations/phil/index.html"},"PHPH-AB":{"title":"Physics and Philosophy - AB","href":"/the-college/concentrations/phph/index.html"},"PHYS-AB":{"title":"Physics - AB","href":"/the-college/concentrations/phys/index.html"},"PHYS-AB-MAPH":{"title":"Physics - AB (Mathematical)","href":"/the-college/concentrations/phys/index.html"},"PHYS-SCB":{"title":"Physics - SCB","href":"/the-college/concentrations/phys/index.html"},"PHYS-SCB-ASPH":{"title":"Physics - SCB (Astrophysics)","href":"/the-college/concentrations/phys/index.html"},"PHYS-SCB-BIPH":{"title":"Physics - SCB (Biological)","href":"/the-college/concentrations/phys/index.html"},"PHYS-SCB-MAPH":{"title":"Physics - SCB (Mathematical)","href":"/the-college/concentrations/phys/index.html"},"POBR-AB":{"title":"Portuguese and Brazilian Studies - AB","href":"/the-college/concentrations/pobr/index.html"},"POLS-AB":{"title":"Political Science - AB","href":"/the-college/concentrations/pols/index.html"},"PSYC-AB":{"title":"Psychology - AB","href":"/the-college/concentrations/psyc/index.html"},"PSYC-SCB":{"title":"Psychology - SCB","href":"/the-college/concentrations/psyc/index.html"},"PUBH-AB":{"title":"Public Health - AB","href":"/the-college/concentrations/pubh/index.html"},"RELS-AB":{"title":"Religious Studies - AB","href":"/the-college/concentrations/rels/index.html"},"SAR-SCB":{"title":"Social Analysis and Research - SCB","href":"/the-college/concentrations/sar/index.html"},"SAR-SCB-ORGA":{"title":"Social Analysis and Research - SCB (Organizational Studies)","href":"/the-college/concentrations/sar/index.html"},"SAST-AB":{"title":"South Asian Studies - AB","href":"/the-college/concentrations/sast/index.html"},"SLAV-AB":{"title":"Slavic Studies - AB","href":"/the-college/concentrations/slav/index.html"},"SOC-AB":{"title":"Sociology - AB","href":"/the-college/concentrations/soc/index.html"},"SOC-AB-ORGA":{"title":"Sociology - AB (Organizational Studies)","href":"/the-college/concentrations/soc/index.html"},"STAT-SCB":{"title":"Statistics - SCB","href":"/the-college/concentrations/stat/index.html"},"STS-AB":{"title":"Science, Technology, and Society - AB","href":"/the-college/concentrations/sts/index.html"},"TAPS-AB":{"title":"Theatre Arts &amp; Performance Stu - AB (No concentration)","href":"/the-college/concentrations/taps/index.html"},"TAPS-AB-PERF":{"title":"Theatre Arts &amp; Performance Studies - AB (Performance Studies)","href":"/the-college/concentrations/taps/index.html"},"TAPS-AB-THTA":{"title":"Theatre Arts &amp; Performance Studies - AB (Theatre Arts)","href":"/the-college/concentrations/taps/index.html"},"TAPS-AB-WPRF":{"title":"Theatre Arts &amp; Performance Studies - AB (Writing for Performance)","href":"/the-college/concentrations/taps/index.html"},"TAPS-AB-DANC":{"title":"Theatre Arts &amp; Performance Studies - AB (Dance)","href":"/the-college/concentrations/taps/index.html"},"URBN-AB":{"title":"Urban Studies - AB","href":"/the-college/concentrations/urbn/index.html"},"VISA-AB":{"title":"Visual Arts - AB","href":"/the-college/concentrations/visa/index.html"},"DTFL-CRT":{"title":"Data Fluency - UG CRT","href":"/the-college/undergraduatecertificates/dtfl/index.html"},"ECT-CRT":{"title":"European Critical Thought - UG CRT","href":"/the-college/undergraduatecertificates/ect/index.html"},"ENSC-CRT":{"title":"Engaged Scholarship - UG CRT","href":"/the-college/undergraduatecertificates/ensc/index.html"},"ENTR-CRT":{"title":"Entrepreneurship - UG CRT","href":"/the-college/undergraduatecertificates/entr/index.html"},"ICC-CRT":{"title":"Intercultural Competence - UG CRT","href":"/the-college/undergraduatecertificates/icc/index.html"},"MIGR-CRT":{"title":"Migration Studies - UG CRT","href":"/the-college/undergraduatecertificates/migr/index.html"}};
sam.config.authURL = 'https://bannerssomgr.brown.edu/ssomanagerPROD/c/SSB?ret_code=PATH';
sam.config.authWindowFeatures = 'height=300,width=400,left=100,top=100';
sam.config.userRecordURL = 'api/?page=sisproxy';
sam.config.sessionTimeout = 86400;
sam.config.textPrimaryCart = 'Primary';
sam.config.tokenParameter = 'access_token';
sam.config.areCartsByCareer = false;
sam.config.showEmptyCareerCarts = false;
sam.config.excludeRegisteredFromPreflight = false;
sam.config.shockAbsorberURL = 'api/?page=shockabsorber';
sam.config.skipShockAbsorber = {"preflight":true,"NOTpreflight":true};
sam.config.preserveP_ = false;
sam.config.isFuse = true;
sam.auth.setMode('token');
