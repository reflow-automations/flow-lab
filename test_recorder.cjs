const vm=require('node:vm');const fs=require('node:fs');const assert=require('node:assert/strict');
let Recorder;const messages=[];
const context={AudioWorkletProcessor:class{constructor(){this.port={postMessage:m=>messages.push(m)}}},Int16Array,Math,registerProcessor:(_name,cls)=>Recorder=cls};
vm.runInNewContext(fs.readFileSync(__dirname+'/web/recorder.js','utf8'),context);
const r=new Recorder();for(let i=0;i<10;i++)r.process([[new Float32Array(128).fill(.5)]]);
r.port.onmessage({data:'stop'});
assert.equal(messages.filter(x=>x.audio).reduce((n,m)=>n+m.audio.byteLength,0),1280*2);
assert.equal(messages.at(-1).done,true);const previous=messages.length;r.process([[new Float32Array(128)]]);assert.equal(messages.length,previous);
console.log('AudioWorklet: alle 1280 samples inclusief laatste deelblok behouden; Stop stopt uitvoer.');
