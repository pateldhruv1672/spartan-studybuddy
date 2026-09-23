const Module=require('module');
const assert=require('assert');
const registeredCommands=[];
let registeredProvider=null;
let saveListener=null;
let statusShown=false;
const config={api:'http://127.0.0.1:8000',projectId:'demo-project',userId:'demo-spartan',indexOnSave:true};
const vscode={
  workspace:{
    getConfiguration:()=>({get:(k)=>config[k],update:async(k,v)=>{config[k]=v}}),
    getWorkspaceFolder:()=>null,
    onDidSaveTextDocument:(fn)=>{saveListener=fn;return {dispose(){}}},
    findFiles:async()=>[],
    fs:{stat:async()=>({size:0})},
    openTextDocument:async()=>({})
  },
  window:{
    activeTextEditor:undefined,
    registerWebviewViewProvider:(id,p)=>{assert.equal(id,'spartan.studyBuddy');registeredProvider=p;return {dispose(){}}},
    createStatusBarItem:()=>({show(){statusShown=true},dispose(){},text:'',command:'',tooltip:''}),
    showInputBox:async()=>undefined,
    showQuickPick:async(items)=>items[0],
    showWarningMessage:()=>{},
    showErrorMessage:()=>{},showInformationMessage:()=>{},setStatusBarMessage:()=>({dispose(){}}),
    withProgress:async(_o,fn)=>fn({report(){}},{isCancellationRequested:false})
  },
  languages:{getDiagnostics:()=>[]},
  commands:{registerCommand:(id,fn)=>{registeredCommands.push(id);return {dispose(){}}},executeCommand:async()=>{}},
  StatusBarAlignment:{Right:2},
  ProgressLocation:{Notification:15},
  ConfigurationTarget:{Global:1,Workspace:2,WorkspaceFolder:3}
};
const orig=Module._load;
Module._load=function(request,parent,isMain){if(request==='vscode')return vscode;return orig(request,parent,isMain)};

const pkg=require('../apps/vscode-extension/package.json');
assert.equal(pkg.contributes.viewsContainers.activitybar[0].icon,'media/spartan.svg','activity bar icon must be a packaged file path');
const extension=require('../apps/vscode-extension/extension.js');
const context={subscriptions:[]};
extension.activate(context);
assert(registeredProvider,'webview provider was not registered');
for(const id of ['spartan.connectProject','spartan.ask','spartan.hint','spartan.explain','spartan.indexWorkspace'])assert(registeredCommands.includes(id),`missing ${id}`);
assert(saveListener,'save listener was not registered');
assert(statusShown,'status bar item was not shown');
let messageHandler=null;
const view={webview:{options:{},html:'',onDidReceiveMessage:(fn)=>{messageHandler=fn},postMessage:()=>{} }};
registeredProvider.resolveWebviewView(view);
assert(view.webview.options.enableScripts===true,'webview scripts disabled');
assert(view.webview.html.includes('Socratic')&&view.webview.html.includes('Connect')&&view.webview.html.includes('Index'),'webview UI missing expected controls');
assert(messageHandler,'webview message handler missing');
console.log('VS Code extension activation contract: PASS');
