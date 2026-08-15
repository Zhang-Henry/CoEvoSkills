import os, sys, numpy as np, pandas as pd
from collections import Counter, defaultdict
from sklearn.cluster import AgglomerativeClustering

scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)
from preprocess import load_sources, remove_prefix_paths, preprocess_dataframe
from embed import compute_embeddings
from naming import (extract_representative_words, ensure_coverage, STOPWORDS)

def run_pipeline(data_dir, output_dir, max_levels=5,
                 top_min=10, top_max=20, child_min=3, child_max=20):
    os.makedirs(output_dir, exist_ok=True)
    print("Phase 1: Loading and preprocessing...")
    df = load_sources(data_dir)
    print(f"  Loaded {len(df)} total paths")
    df = remove_prefix_paths(df)
    print(f"  After prefix removal: {len(df)} leaf paths")
    df = preprocess_dataframe(df)
    print(f"  Source distribution: {df['source'].value_counts().to_dict()}")

    print("Phase 2: Computing embeddings...")
    embeddings = compute_embeddings(df['norm_path'].tolist(), batch_size=512)
    print(f"  Embeddings shape: {embeddings.shape}")

    print("Phase 3: Building hierarchy...")
    n = len(df)
    nll = df['norm_levels'].tolist()
    sources = df['source'].tolist()
    lcols = {i: [None]*n for i in range(1, max_levels+1)}

    # Level 1
    print("  Level 1 clustering...")
    l1_labels = agglom_cluster(embeddings, 20)
    l1_groups = group_by_label(l1_labels)
    
    # Iteratively: merge single-source, split to reach top_min, repeat until stable
    for outer in range(10):
        # Merge ALL single-source clusters
        merge_single_source(l1_groups, l1_labels, sources, embeddings)
        
        # Check if we need to split
        if len(l1_groups) >= top_min:
            break
        
        # Split largest to reach top_min, but only if both halves are multi-source
        split_done = False
        while len(l1_groups) < top_min:
            # Try to split the largest cluster into multi-source halves
            candidates = sorted(l1_groups.keys(), key=lambda k: -len(l1_groups[k]))
            found_split = False
            for cid in candidates:
                if len(l1_groups[cid]) < 30: continue
                indices = l1_groups[cid]
                sl = agglom_cluster(embeddings[indices], 2)
                ga = [indices[i] for i,l in enumerate(sl) if l==0]
                gb = [indices[i] for i,l in enumerate(sl) if l==1]
                if min(len(ga),len(gb)) < 5: continue
                # Check both halves are multi-source
                mfa = max(Counter(sources[i] for i in ga).values())/len(ga)
                mfb = max(Counter(sources[i] for i in gb).values())/len(gb)
                if mfa <= 0.95 and mfb <= 0.95:
                    nid = max(l1_groups.keys())+1
                    del l1_groups[cid]
                    l1_groups[cid]=ga; l1_groups[nid]=gb
                    for i in ga: l1_labels[i]=cid
                    for i in gb: l1_labels[i]=nid
                    found_split = True
                    break
            if not found_split:
                # Can't split without creating single-source, just split largest anyway
                largest = max(l1_groups, key=lambda k: len(l1_groups[k]))
                if len(l1_groups[largest]) < 30: break
                indices = l1_groups[largest]
                sl = agglom_cluster(embeddings[indices], 2)
                ga = [indices[i] for i,l in enumerate(sl) if l==0]
                gb = [indices[i] for i,l in enumerate(sl) if l==1]
                if min(len(ga),len(gb)) < 5: break
                nid = max(l1_groups.keys())+1
                del l1_groups[largest]
                l1_groups[largest]=ga; l1_groups[nid]=gb
                for i in ga: l1_labels[i]=largest
                for i in gb: l1_labels[i]=nid
                split_done = True
                break  # Will re-check single-source in next outer iteration
        
        if not split_done and len(l1_groups) >= top_min:
            break
    
    while len(l1_groups) > top_max:
        sm = min(l1_groups, key=lambda k: len(l1_groups[k]))
        merge_into(l1_groups, l1_labels, embeddings, sm)

    # Verify
    for cid in list(l1_groups.keys()):
        sc = Counter(sources[i] for i in l1_groups[cid])
        mf = max(sc.values())/len(l1_groups[cid])
        if mf > 0.95:
            print(f"    WARNING: still single-source cluster {cid}: {len(l1_groups[cid])} items")

    # Name
    l1n = name_clusters(l1_groups, nll, set())
    for cid in l1n: l1n[cid] = expand_name(l1n[cid], l1_groups[cid], nll, set(), 3)
    l1n = resolve_overlaps(l1n, l1_groups, nll, set())
    for cid, indices in l1_groups.items():
        for i in indices: lcols[1][i] = l1n[cid]
    
    print(f"    Level 1 final: {len(l1_groups)} clusters")
    for cid in sorted(l1_groups.keys(), key=lambda k: -len(l1_groups[k])):
        sc = Counter(sources[i] for i in l1_groups[cid])
        mf = max(sc.values())/sum(sc.values())
        f = " ***" if mf>0.95 else ""
        print(f"      {l1n[cid]}: {len(l1_groups[cid])} {dict(sc)}{f}")

    # Levels 2-5
    for level in range(2, max_levels+1):
        print(f"  Level {level} clustering...")
        pgroups = defaultdict(list)
        for i in range(n):
            pk = tuple(lcols[l][i] for l in range(1, level))
            if all(p is not None for p in pk): pgroups[pk].append(i)
        lc = 0
        for pk, indices in pgroups.items():
            mi = child_min*(2+level)
            if len(indices) < mi: continue
            ns = determine_n_sub(len(indices), child_min, child_max)
            se = embeddings[indices]
            sl = agglom_cluster(se, ns)
            sg = glm(sl, indices)
            sg = merge_small(sg, embeddings, 3)
            if len(sg)<child_min:
                if len(indices)>=child_min*4:
                    sl = agglom_cluster(se, child_min)
                    sg = glm(sl, indices)
                    sg = merge_small(sg, embeddings, 3)
                if len(sg)<child_min: continue
            while len(sg)>child_max:
                sm=min(sg,key=lambda k:len(sg[k]))
                merge_sub(sg, embeddings, sm)
            sg = merge_small(sg, embeddings, 3)
            if len(sg)<child_min: continue
            pw = get_pw(pk)
            sn = name_clusters(sg, nll, pw)
            for scid in sn: sn[scid] = expand_name(sn[scid], sg[scid], nll, pw, 3)
            sn = resolve_overlaps(sn, sg, nll, pw)
            if len(sg)>child_min:
                sn, sg = merge_overlap_siblings(sn, sg, nll, pw, embeddings, child_min)
            if len(sg)<child_min: continue
            for scid in list(sn.keys()):
                sn[scid] = fix_pc(sn[scid], pk)
                sn[scid] = expand_name(sn[scid], sg[scid], nll, pw, 3)
            sn = resolve_overlaps(sn, sg, nll, pw)
            if len(sg)>child_min:
                sn, sg = merge_overlap_siblings(sn, sg, nll, pw, embeddings, child_min)
            if len(sg)<child_min: continue
            for scid, si in sg.items():
                for i in si: lcols[level][i] = sn[scid]
            lc += len(sg)
        print(f"    Level {level}: {lc} total clusters")

    print("Phase 4: Building output...")
    for lvl in range(1, max_levels+1): df[f'unified_level_{lvl}'] = lcols[lvl]
    dc = [f'unified_level_{i}' for i in range(1, max_levels+1)]
    df['depth'] = df[dc].notna().sum(axis=1).clip(lower=1).astype(int)
    oc = ['source','category_path','depth']+dc
    full = df[oc].copy()
    fp = os.path.join(output_dir, 'unified_taxonomy_full.csv')
    full.to_csv(fp, index=False)
    print(f"  Written: {fp} ({len(full)} rows)")
    hier = df[dc].drop_duplicates().sort_values(dc).reset_index(drop=True).fillna('')
    hp = os.path.join(output_dir, 'unified_taxonomy_hierarchy.csv')
    hier.to_csv(hp, index=False)
    print(f"  Written: {hp} ({len(hier)} rows)")
    return full, hier

def merge_single_source(groups, labels, sources, emb):
    for _ in range(30):
        any_m = False
        ss_ids = []
        for cid in groups:
            sc = Counter(sources[i] for i in groups[cid])
            if max(sc.values())/len(groups[cid]) > 0.95:
                ss_ids.append(cid)
        ss_ids.sort(key=lambda k: len(groups[k]))
        if not ss_ids: break
        for cid in ss_ids:
            if cid not in groups: continue
            ms = {k:v for k,v in groups.items() if k!=cid and
                  max(Counter(sources[i] for i in v).values())/len(v)<=0.95}
            if not ms: ms = {k:v for k,v in groups.items() if k!=cid}
            if ms:
                nr = find_nearest(groups[cid], ms, emb)
                groups[nr].extend(groups[cid])
                for i in groups[cid]: labels[i]=nr
                del groups[cid]; any_m=True
        if not any_m: break

def agglom_cluster(emb, nc):
    n=len(emb)
    if n<=nc: return list(range(n))
    return AgglomerativeClustering(n_clusters=min(nc,n),metric='cosine',linkage='average').fit_predict(emb).tolist()

def group_by_label(labels):
    g=defaultdict(list)
    for i,l in enumerate(labels): g[l].append(i)
    return dict(g)

def glm(labels, indices):
    g=defaultdict(list)
    for j,l in enumerate(labels): g[l].append(indices[j])
    return dict(g)

def merge_into(groups, labels, emb, cid):
    idx=groups.pop(cid); nr=find_nearest(idx,groups,emb)
    groups[nr].extend(idx)
    for i in idx: labels[i]=nr

def merge_small(groups, emb, ms=3):
    ch=True
    while ch:
        ch=False
        for t in [k for k,v in groups.items() if len(v)<ms]:
            if t not in groups or len(groups)<=1: continue
            nr=find_nearest(groups[t],{k:v for k,v in groups.items() if k!=t},emb)
            groups[nr].extend(groups[t]); del groups[t]; ch=True
    return groups

def merge_sub(groups, emb, cid):
    idx=groups.pop(cid); nr=find_nearest(idx,groups,emb); groups[nr].extend(idx)

def merge_overlap_siblings(names, groups, nll, pw, emb, cm):
    for _ in range(10):
        merged=False
        ids=list(names.keys())
        for i in range(len(ids)):
            if ids[i] not in names: continue
            for j in range(i+1, len(ids)):
                if ids[j] not in names or len(names)<=cm: continue
                if not no_overlap(names[ids[i]], names[ids[j]]):
                    ci,cj=ids[i],ids[j]
                    keep,rem=(ci,cj) if len(groups[ci])>=len(groups[cj]) else (cj,ci)
                    groups[keep].extend(groups[rem])
                    del groups[rem]; del names[rem]
                    cn=[nll[x] for x in groups[keep]]
                    nm=extract_representative_words(cn,pw,max_words=4)
                    nm,_=ensure_coverage(nm,cn,pw,0.7,5)
                    names[keep]=expand_name(nm,groups[keep],nll,pw,3)
                    merged=True; break
            if merged: break
        if not merged: break
        for scid in list(names.keys()):
            names[scid]=expand_name(names[scid],groups[scid],nll,pw,3)
        names=resolve_overlaps(names,groups,nll,pw)
    return names, groups

def find_nearest(indices, groups, emb):
    if not groups: return None
    c=emb[indices].mean(axis=0); cn=max(np.linalg.norm(c),1e-10)
    best,bs=None,-2
    for gid,gi in groups.items():
        gc=emb[gi].mean(axis=0); gn=max(np.linalg.norm(gc),1e-10)
        s=np.dot(c,gc)/(cn*gn)
        if s>bs: bs,best=s,gid
    return best

def determine_n_sub(ni, cm=3, cx=20):
    if ni<cm*3: return cm
    if ni<=30: return max(cm,min(cx,ni//5))
    if ni<=100: return max(cm,min(cx,int(np.sqrt(ni))))
    if ni<=500: return max(cm,min(cx,int(ni**0.4)))
    return max(cm,min(cx,int(ni**0.35)))

def get_pw(pk):
    w=set()
    for p in pk:
        if p:
            for x in p.lower().replace(' | ',' ').split(): w.add(x)
    return w

def name_clusters(groups, nll, pw):
    names={}
    for cid,indices in groups.items():
        cn=[nll[i] for i in indices]
        nm=extract_representative_words(cn,pw,max_words=4)
        nm,_=ensure_coverage(nm,cn,pw,0.7,5)
        names[cid]=nm
    return names

def expand_name(name, indices, nll, pw, min_words=3):
    if not name or name.strip()=='' or name.lower() in ('general','none','other'):
        cn=[nll[i] for i in indices]
        name=extract_representative_words(cn,set(),max_words=4)
    parts=[p.strip() for p in name.split(' | ') if p.strip()]
    if len(parts)<min_words:
        wf=Counter()
        ex=set(p.lower() for p in parts)
        for norms in [nll[i] for i in indices]:
            for lvl in norms:
                for w in lvl.split():
                    if w not in STOPWORDS and len(w)>1 and w.lower() not in ex and w.lower() not in pw:
                        wf[w]+=1
        for tw,_ in wf.most_common(10):
            if len(parts)>=min_words: break
            if tw.title() not in parts: parts.append(tw.title())
    return ' | '.join(parts[:5])

def resolve_overlaps(names, groups, nll, pw):
    if not isinstance(names,dict): return names
    nl=list(names.values()); il=list(names.keys())
    for _ in range(25):
        changed=False
        for i in range(len(nl)):
            if il[i] not in groups: continue
            wi=set(nl[i].lower().replace(' | ',' ').split())
            for j in range(i+1, len(nl)):
                if il[j] not in groups: continue
                wj=set(nl[j].lower().replace(' | ',' ').split())
                if not wi or not wj: continue
                ov=len(wi&wj)/min(len(wi),len(wj))
                if ov<=0.3: continue
                ci,cj=il[i],il[j]
                if len(groups[ci])>=len(groups[cj]): ti,ki,tc,kw=j,i,cj,wi
                else: ti,ki,tc,kw=i,j,ci,wj
                ow=wi&wj; ex=pw|kw
                cn=[nll[x] for x in groups[tc]]
                nn=extract_representative_words(cn,ex,max_words=5)
                if nn and no_overlap(nn,nl[ki]): nl[ti]=nn; changed=True; continue
                tp=nl[ti].split(' | ')
                nop=[p for p in tp if p.lower() not in ow]
                uwf=Counter()
                for norms in cn:
                    for lvl in norms:
                        for w in lvl.split():
                            if w not in STOPWORDS and len(w)>1 and w not in ex and w not in ow: uwf[w]+=1
                np2=nop[:2]
                for w,_ in uwf.most_common(10):
                    if len(np2)>=4: break
                    if w.title() not in np2: np2.append(w.title())
                if len(np2)>=3:
                    nn=' | '.join(np2[:5])
                    if no_overlap(nn,nl[ki]): nl[ti]=nn; changed=True; continue
                if uwf:
                    tu=[w.title() for w,_ in uwf.most_common(5)]
                    if len(tu)>=3:
                        nn=' | '.join(tu[:5])
                        if no_overlap(nn,nl[ki]): nl[ti]=nn; changed=True; continue
                aw=Counter()
                for norms in cn:
                    for lvl in norms:
                        for w in lvl.split():
                            if w not in STOPWORDS and len(w)>2: aw[w]+=1
                found=False
                for w,_ in aw.most_common(50):
                    if w not in kw and w not in pw:
                        cp=nop[:1]+[w.title()]
                        for w2,_ in aw.most_common(50):
                            if w2!=w and w2 not in kw and w2 not in pw and len(cp)<4:
                                cp.append(w2.title())
                        if len(cp)>=3:
                            nn=' | '.join(cp[:5])
                            if no_overlap(nn,nl[ki]): nl[ti]=nn; changed=True; found=True; break
                if found: continue
        if not changed: break
    return {c:nm for c,nm in zip(il,nl) if c in groups}

def no_overlap(a,b,t=0.3):
    wa=set(a.lower().replace(' | ',' ').split())
    wb=set(b.lower().replace(' | ',' ').split())
    if not wa or not wb: return True
    return len(wa&wb)/min(len(wa),len(wb))<=t

def fix_pc(cn,pk):
    pw=get_pw(pk)
    parts=[p for p in cn.split(' | ') if p.lower() not in pw]
    return ' | '.join(parts) if parts else cn

if __name__=='__main__': run_pipeline('/root/data','/root/output')
