"""Read-only coverage sizing; never a production cache or placement decision."""
from pathlib import Path
from collections import defaultdict
import csv, hashlib, json, re, sys, time
CIGAR=re.compile(r"([1-9][0-9]*)([MIDN=X])")

def merged(rows, close_below=1):
    out=[]
    for start,end in sorted(rows):
        if out and start-out[-1][1]<close_below:
            out[-1][1]=max(out[-1][1],end)
        else:out.append([start,end])
    return out

def missing(length, rows, minimum=100):
    out=[]; cursor=0
    for start,end in merged(rows):
        if start-cursor>=minimum:out.append([cursor,start])
        cursor=max(cursor,end)
    if length-cursor>=minimum:out.append([cursor,length])
    return out

def blocks(cigar, qs, qe, ts, te, strand, minimum=100):
    """Closing sub-threshold holes preserves all >=minimum uncovered intervals."""
    q=qs if strand=="+" else qe; t=ts; last_end=0; covered=[]; has_paired=False
    for match in CIGAR.finditer(cigar):
        if match.start()!=last_end:raise ValueError("invalid CIGAR")
        last_end=match.end(); n=int(match[1]);op=match[2]
        if op in "M=X":has_paired=True
        if op in "MI=X":
            q1=q+n if strand=="+" else q-n
            if op in "M=":
                start,end=sorted((q,q1))
                if covered and strand=="+" and start-covered[-1][1]<minimum:covered[-1][1]=end
                elif covered and strand=="-" and covered[-1][0]-end<minimum:covered[-1][0]=start
                else:covered.append([start,end])
            q=q1
        if op in "MDN=X":t+=n
    if last_end!=len(cigar) or not last_end or q!=(qe if strand=="+" else qs) or t!=te:raise ValueError("CIGAR geometry mismatch")
    return covered,has_paired

def diagnose(root,out):
    started=time.monotonic(); results=[]; records=[]
    with (root/"metadata/datasets.tsv").open() as f: datasets=list(csv.DictReader(f,delimiter="\t"))
    for dataset in datasets:
        name=dataset["dataset_name"]
        with (root/dataset["fai_relpath"]).open() as f:lengths={r[0]:int(r[1]) for r in (l.split("\t") for l in f)}
        path=root/("runs/"+name+"_vs_ref/result.paf"); before=path.stat(); digest=hashlib.sha256(); coverage=defaultdict(list); present=set(); count=0
        with path.open("rb") as f:
            for raw in f:
                digest.update(raw)
                if not raw.strip() or raw.startswith(b"#"):continue
                fields=raw.decode("ascii").rstrip("\r\n").split("\t");count+=1
                qname=fields[0];qlen,qs,qe=map(int,fields[1:4]);ts,te=map(int,fields[7:9]);matches,span,mapq=map(int,fields[9:12]);strand=fields[4]
                assert qlen==lengths[qname] and 0<=qs<qe<=qlen and strand in ["+","-"] and span>0
                cigars=[tag[5:] for tag in fields[12:] if tag.startswith("cg:Z:")];assert len(cigars)==1
                if matches/span>=0.9 and 20<=mapq<255:
                    rows,used=blocks(cigars[0],qs,qe,ts,te,strand)
                    if used:present.add(qname);coverage[qname].extend(rows)
                elif re.search("[M=X]",cigars[0]):present.add(qname)
                if count%100000==0: print(json.dumps({"dataset":name,"paf_rows":count,"phase":"coverage_scan"}),flush=True)
        after=path.stat();assert (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        sums={str(flank):0 for flank in [0,1000,10000,100000]};counts={k:0 for k in sums};longest={k:0 for k in sums};query_bp=0;nqueries=0;ngaps=0
        for qname in sorted(present):
            gaps=missing(lengths[qname],coverage[qname])
            if not gaps:continue
            nqueries+=1;query_bp+=lengths[qname];ngaps+=len(gaps)
            records.append({"dataset":name,"contig":qname,"length":lengths[qname],"uncovered":gaps})
            for key in sums:
                flank=int(key); windows=merged([[max(0,s-flank),min(lengths[qname],e+flank)] for s,e in gaps]);sizes=[e-s for s,e in windows]
                sums[key]+=sum(sizes);counts[key]+=len(sizes);longest[key]=max(longest[key],max(sizes))
        row={"dataset":name,"paf_rows":count,"reference_paf_sha256":digest.hexdigest(),"source_count":len(lengths),"reference_candidate_sources":len(present),"partial_query_count":nqueries,"whole_query_bp":query_bp,"uncovered_intervals":ngaps,"window_total_bp_by_flank":sums,"window_count_by_flank":counts,"window_max_bp_by_flank":longest}
        results.append(row);print(json.dumps(row),flush=True)
    report={"policy":"read-only sizing using original whole sources; >=100bp holes; not cache acceptance or a change to scientific policy; assumes no long-N source splits, compare count/bp to current task before use","datasets":results,"wall_seconds":time.monotonic()-started}
    out.mkdir(exist_ok=True);(out/"partial-coverage.json").write_text(json.dumps(records)+"\n");(out/"summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)

if __name__=="__main__":diagnose(Path(sys.argv[1]),Path.cwd())
