"""Extract HWP5 paragraph text; retain neither control fields nor fabricated missing content."""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
def extract(path):
    import olefile
    with olefile.OleFileIO(path) as ole:
        header=ole.openstream("FileHeader").read()
        flags=struct.unpack_from("<I",header,36)[0]
        if flags&2:raise ValueError("암호화 HWP: 수동 확인 필요")
        parts=[]
        for name in sorted(ole.listdir()):
            if len(name)!=2 or name[0]!="BodyText" or not name[1].startswith("Section"):continue
            data=ole.openstream(name).read()
            if flags&1:data=zlib.decompress(data,-15)
            i=0
            while i+4<=len(data):
                h=struct.unpack_from("<I",data,i)[0];i+=4;tag=h&1023;size=h>>20
                if size==4095:size=struct.unpack_from("<I",data,i)[0];i+=4
                body=data[i:i+size];i+=size
                if tag!=67:continue
                units=struct.unpack("<"+"H"*(len(body)//2),body);clean=[];j=0
                while j<len(units):
                    code=units[j]
                    if code<32:
                        if code in {2,3,4,5,6,7,8,9,11,12,14,15,16,17,18,19,20,21,22,23}:j+=8
                        else:j+=1
                        clean.append(" ");continue
                    clean.append(chr(code));j+=1
                parts.append("".join(clean))
    return "\n".join(parts)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--input",action="append",required=True);p.add_argument("--output-dir",required=True);p.add_argument("--report",required=True);a=p.parse_args()
 out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True);result=[]
 for path in a.input:
  src=Path(path)
  try:
   text=extract(src);(out/(src.name+".txt")).write_text(text)
   result.append({"file":src.name,"sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"characters":len(text),"success":True,"sejong_source_15106191":"15106191" in text})
  except Exception as error:result.append({"file":src.name,"success":False,"reason":str(error),"manual_check":["원문 출처URL","분석 기간","후보 점수 산식","OD 제외조건"]})
 Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
