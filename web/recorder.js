class PCMRecorder extends AudioWorkletProcessor {
  constructor(options={}){super();this.data=new Int16Array(960);this.index=0;this.active=true;this.frames=0;this.maxFrames=options.processorOptions?.maxFrames??7200000;this.port.onmessage=e=>{if(e.data==='stop'){this.flush();this.active=false;this.port.postMessage({done:true})}}}
  flush(){if(this.index){const b=this.data.slice(0,this.index).buffer;this.port.postMessage({audio:b},[b]);this.index=0}}
  process(inputs){if(!this.active)return false;const data=inputs[0]?.[0];if(data)for(const value of data){if(this.frames>=this.maxFrames)break;this.data[this.index++]=Math.round(Math.max(-1,Math.min(1,value))*32767);this.frames++;if(this.index===960)this.flush()}if(this.frames>=this.maxFrames){this.flush();this.active=false;this.port.postMessage({done:true,limit:true});return false}return true}
}
registerProcessor('pcm-recorder',PCMRecorder);
