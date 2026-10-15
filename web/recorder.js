class PCMRecorder extends AudioWorkletProcessor {
  constructor(){super();this.data=new Int16Array(960);this.index=0;this.active=true;this.port.onmessage=e=>{if(e.data==='stop'){this.flush();this.active=false;this.port.postMessage({done:true})}}}
  flush(){if(this.index){const b=this.data.slice(0,this.index).buffer;this.port.postMessage({audio:b},[b]);this.index=0}}
  process(inputs){if(!this.active)return false;const data=inputs[0]?.[0];if(data)for(const value of data){this.data[this.index++]=Math.round(Math.max(-1,Math.min(1,value))*32767);if(this.index===960)this.flush()}return true}
}
registerProcessor('pcm-recorder',PCMRecorder);
