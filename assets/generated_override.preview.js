/* Managed by FlClash strategy_manager.py. */
function main(config) {
  if (!config || typeof config !== 'object') return config;
  var cleanMembers = [];
  var stableMembers = [];
  var fastMembers = [];
  var proxyNames = [];
  var rawProxies = Array.isArray(config.proxies) ? config.proxies : [];
  var infoPattern = /(剩余|流量|套餐|官网|订阅|到期|重置|客服|公告|更新|实时负载|使用说明|traffic|expire|website|reset|official|subscribe)/i;
  for (var i = 0; i < rawProxies.length && proxyNames.length < 180; i++) {
    var name = rawProxies[i] && rawProxies[i].name;
    if (typeof name === 'string' && name && !infoPattern.test(name) && proxyNames.indexOf(name) < 0) proxyNames.push(name);
  }
  function validMembers(items) {
    var out = [];
    for (var j = 0; j < items.length; j++) {
      if (proxyNames.indexOf(items[j]) >= 0 && out.indexOf(items[j]) < 0) out.push(items[j]);
    }
    return out;
  }
  cleanMembers = validMembers(cleanMembers);
  stableMembers = validMembers(stableMembers);
  fastMembers = validMembers(fastMembers);
  if (!fastMembers.length) fastMembers = proxyNames.slice(0, 20);
  function membersOrReject(items) { return items.length ? items : ['REJECT']; }
  config['proxy-groups'] = [
    {name:'净选',type:'url-test',proxies:membersOrReject(cleanMembers),url:'https://api.openai.com/v1/models','expected-status':'401',interval:600,lazy:false,timeout:8000,'max-failed-times':2,tolerance:40,hidden:false},
    {name:'稳净',type:'url-test',proxies:membersOrReject(stableMembers),url:'https://www.gstatic.com/generate_204','expected-status':'204',interval:600,lazy:false,timeout:8000,'max-failed-times':2,tolerance:30,hidden:false},
    {name:'极速',type:'url-test',proxies:membersOrReject(fastMembers),url:'https://speed.cloudflare.com/__down?bytes=131072','expected-status':'200',interval:600,lazy:false,timeout:8000,'max-failed-times':2,tolerance:60,hidden:false}
  ];
  config.rules = ["DOMAIN-SUFFIX,local,DIRECT", "DOMAIN-SUFFIX,lan,DIRECT", "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve", "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve", "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve", "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve", "IP-CIDR,224.0.0.0/4,DIRECT,no-resolve", "IP-CIDR6,::1/128,DIRECT,no-resolve", "IP-CIDR6,fc00::/7,DIRECT,no-resolve", "DOMAIN-SUFFIX,openai.com,净选", "DOMAIN-SUFFIX,chatgpt.com,净选", "DOMAIN-SUFFIX,oaistatic.com,净选", "DOMAIN-SUFFIX,oaiusercontent.com,净选", "DOMAIN-SUFFIX,google.com,净选", "DOMAIN-SUFFIX,googleapis.com,净选", "DOMAIN-SUFFIX,gstatic.com,净选", "DOMAIN-SUFFIX,gemini.google.com,净选", "DOMAIN-SUFFIX,cloudflare.com,净选", "MATCH,极速"];
  config.mode = 'rule';
  config['allow-lan'] = false;
  config['bind-address'] = '127.0.0.1';
  config.ipv6 = false;
  config['tcp-concurrent'] = true;
  config['unified-delay'] = true;
  config.dns = {"enable": true, "listen": "127.0.0.1:1053", "cache-algorithm": "arc", "prefer-h3": false, "use-hosts": true, "use-system-hosts": false, "respect-rules": true, "ipv6": false, "default-nameserver": ["1.1.1.1", "8.8.8.8"], "enhanced-mode": "fake-ip", "fake-ip-range": "198.18.0.1/16", "fake-ip-filter-mode": "blacklist", "fake-ip-filter": ["*.lan", "*.local", "localhost", "localhost.*"], "nameserver": ["https://1.1.1.1/dns-query#极速", "https://8.8.8.8/dns-query#极速"], "proxy-server-nameserver": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"], "fallback": [], "nameserver-policy": {}};
  var tun = config.tun && typeof config.tun === 'object' ? config.tun : {};
  tun.enable = true;
  tun.device = 'FlClash';
  tun.stack = 'mixed';
  tun['auto-route'] = true;
  tun['auto-detect-interface'] = true;
  tun['dns-hijack'] = ['any:53','tcp://any:53'];
  tun['strict-route'] = true;
  tun['endpoint-independent-nat'] = false;
  tun['route-address'] = [];
  config.tun = tun;
  var listeners = [];
  var existing = Array.isArray(config.listeners) ? config.listeners : [];
  for (var k = 0; k < existing.length; k++) {
    if (!existing[k] || String(existing[k].name || '').indexOf('__flt_') !== 0) listeners.push(existing[k]);
  }
  for (var n = 0; n < proxyNames.length; n++) {
    listeners.push({name:'__flt_' + ('000' + n).slice(-3),type:'mixed',port:23000+n,listen:'127.0.0.1',proxy:proxyNames[n],udp:false,users:[]});
  }
  config.listeners = listeners;
  return config;
}
