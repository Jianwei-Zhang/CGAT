/* Read pre-DP state through the UNMODIFIED minimap2 v2.31 library API.
 * No CIGAR/DP mapping, no binary interposition, no patch to minimap2 sources.
 * Build only with the pinned clean source via build_native_chain_state.py.
 * Upstream license: MINIMAP2_LICENSE.txt. This companion is NOT minimap2.
 */
#define _FILE_OFFSET_BITS 64
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <ctype.h>
#include <inttypes.h>
#include <limits.h>
#include <locale.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include "minimap.h"
#include "mmpriv.h"

static int integer(const char *text, int64_t low, int64_t high, int64_t *out)
{
    char *end;
    int64_t value;
    if (!text || !*text || *text == '+' || *text == '-') return 0;
    errno = 0;
    value = strtoll(text, &end, 10);
    if (errno || *end || value < low || value > high) return 0;
    *out = value;
    return 1;
}

static int token(const char *text)
{
    size_t n = 0;
    for (; *text; ++text, ++n)
        if ((unsigned char)*text < 33 || (unsigned char)*text > 126 || n >= 4096) return 0;
    return n > 0;
}

/* Evaluate only native hit-sort/parent/secondary/MAPQ over caller-proven
 * post-skeleton metadata. NO CIGAR words are allocated, normalized or scored.
 * Inversions, segments, alt references and splice modes are not accepted here.
 * The caller must supply complete original-state/path/anchor provenance. */
static int select_metadata(const char *path)
{
    FILE *input = fopen(path,"rb");
    int qlen, rep, count, original, i, j, expected, trailing;
    int64_t v[18], sum = 0;
    mm_reg1_t *r;
    mm_idxopt_t io;
    mm_mapopt_t mo;
    if (!input || fscanf(input,"CGAT_POST_DP_V1 %d %d %d",&qlen,&rep,&count) != 3
            || qlen < 1 || rep < 0 || rep > qlen || count < 0 || count > 100000) return 2;
    original = count;
    r = (mm_reg1_t*)calloc(count? count : 1,sizeof(*r));
    if (!r) return 3;
    for (i = 0; i < count; ++i) {
        mm_reg1_t *x = &r[i];
        for (j = 0; j < 18; ++j) {
            char text[64];
            if (fscanf(input,"%63s",text) != 1
                    || !integer(text,0,j == 17? UINT32_MAX : INT32_MAX,&v[j])) return 2;
        }
        if (v[0] != i || v[1] >= v[2] || v[2] > qlen || v[4] >= v[5] || v[6] > 1
                || v[7] > INT32_MAX-38 || v[8] < 1 || v[9] < 3 || v[10] < 40
                || v[10] > v[11] || v[12] < 200 || v[15] > INT32_MAX-original) return 2;
        x->as = i; /* Input identity only; downstream functions never use as. */
        x->qs = v[1], x->qe = v[2], x->rid = v[3], x->rs = v[4], x->re = v[5], x->rev = v[6];
        x->score = v[7], x->score0 = v[8], x->cnt = v[9], x->mlen = v[10], x->blen = v[11];
        x->subsc = v[14], x->n_sub = v[15], x->hash = (uint32_t)v[17];
        x->p = (mm_extra_t*)calloc(1,sizeof(mm_extra_t));
        if (!x->p) return 3;
        x->p->dp_max = v[12], x->p->dp_max0 = v[13], x->p->dp_max2 = v[16];
    }
    if (fscanf(input," END %d",&expected) != 1 || expected != original) return 2;
    while ((trailing = fgetc(input)) != EOF)
        if (!isspace((unsigned char)trailing)) return 2;
    if (ferror(input)) return 3;
    fclose(input);
    if (mm_set_opt(0,&io,&mo) || mm_set_opt("asm10",&io,&mo)) return 2;
    mm_hit_sort(0,&count,r,mo.alt_drop);
    mm_set_parent(0,mo.mask_level,mo.mask_len,count,r,mo.a*2+mo.b,
                  !!(mo.flag&MM_F_HARD_MLEVEL),mo.alt_drop);
    mm_select_sub(0,mo.pri_ratio,io.k*2,mo.best_n,0,mo.max_gap*0.8,&count,r);
    mm_set_sam_pri(count,r);
    for (i = 0; i < count; ++i)
        if (r[i].id == r[i].parent) sum += r[i].score;
    if (count && sum <= 0) return 2; /* Avoid undefined native 0/0 confidence. */
    /* Guard native float-to-int overflow; reject unsupported arithmetic, never
     * replace the original MAPQ formula with a guessed/clipped result. Source
     * expressions below are only range preflight; the library returns MAPQ. */
    for (i = 0; i < count; ++i) {
        mm_reg1_t *x = &r[i];
        if (x->n_sub == INT32_MAX) return 2;
        if (x->id == x->parent) {
            float unique = (float)sum / (sum+rep);
            float pen = (x->score > 100? 1.0f : 0.01f*x->score)*unique;
            float cm = x->cnt > 10? 1.0f : 0.1f*x->cnt;
            float identity = (float)x->mlen/x->blen, ratio, raw, alternate;
            int sub = x->subsc > mo.min_chain_score? x->subsc : mo.min_chain_score;
            int64_t integer, penalty;
            pen = pen < cm? pen : cm;
            if (x->p->dp_max2 > 0) {
                ratio = (float)x->p->dp_max2*sub/x->p->dp_max/x->score0;
                raw = identity*pen*40.0f*(1.0f-ratio*ratio)*logf((float)x->p->dp_max/mo.a);
                alternate = 6.02f*identity*identity*(x->p->dp_max-x->p->dp_max2)/mo.a+.499f;
                if (!isfinite(alternate) || alternate >= 2147483648.0f || alternate < -2147483648.0f) return 2;
            } else {
                ratio = (float)sub/x->score0;
                raw = identity*pen*40.0f*(1.0f-ratio)*logf((float)x->p->dp_max/mo.a);
                alternate = raw;
            }
            if (!isfinite(raw) || raw >= 2147483648.0f || raw < -2147483648.0f) return 2;
            integer = (int64_t)raw;
            if ((int64_t)alternate < integer) integer = (int64_t)alternate;
            penalty = (int64_t)(4.343f*logf(x->n_sub+1)+.499f);
            if (integer-penalty < INT32_MIN) return 2;
        }
    }
    mm_set_mapq2(0,count,r,mo.min_chain_score,mo.a,rep,0,0);
    printf("S\tcgat-post-dp\t1\t%s\tasm10\t%d\t%d\t%d\t%d\n",MM_VERSION,qlen,rep,original,count);
    for (i = 0; i < count; ++i) {
        printf("R\t%d\t%d\t%d\t%d\t%d\t%d\t%u\t%u\n",r[i].as,r[i].id,r[i].parent,
               r[i].subsc,r[i].n_sub,r[i].p->dp_max2,(unsigned)r[i].mapq,(unsigned)r[i].sam_pri);
        free(r[i].p);
    }
    printf("END\t%d\n",count);
    free(r);
    return fflush(stdout)? 3 : 0;
}

int main(int argc, char **argv)
{
    int64_t mid, part, offset, length;
    FILE *idx_file, *seq_file;
    mm_idx_t *index;
    mm_tbuf_t *buffer;
    mm_idxopt_t io;
    mm_mapopt_t mo;
    mm_reg1_t *regions;
    mm_bseq1_t query;
    char *sequence;
    kstring_t paf = {0,0,0};
    int i, n_regions;
    double start;
    if (!setlocale(LC_NUMERIC,"C") || strcmp(MM_VERSION, "2.31-r1302")) return 2;
    if (argc == 3 && !strcmp(argv[1],"--select")) return select_metadata(argv[2]);
    if (argc == 2 && !strcmp(argv[1], "--version")) {
        printf("cgat-chain-state\t1\t%s\tasm10\n", MM_VERSION);
        return ferror(stdout)? 3 : 0;
    }
    /* index-part, inherited mid_occ, original part number, original query ID,
     * private unwrapped sequence spool, byte offset, whole-record length. */
    if (argc != 8 || !integer(argv[2],1,INT32_MAX,&mid)
            || !integer(argv[3],0,9999,&part) || !token(argv[4])
            || !integer(argv[6],0,INT64_MAX,&offset)
            || !integer(argv[7],1,INT32_MAX,&length) || offset > INT64_MAX-length) return 2;
    mm_verbose = 2;
    mm_dbg_flag = MM_DBG_PRINT_CHAIN;
    mm_realtime0 = realtime();
    if (mm_set_opt(0,&io,&mo) || mm_set_opt("asm10",&io,&mo)) return 2;
    if (mo.flag & (MM_F_CIGAR|MM_F_OUT_CG|MM_F_ALL_CHAINS)) return 2;
    idx_file = fopen(argv[1],"rb");
    if (!idx_file) return 3;
    index = mm_idx_load(idx_file);
    if (!index || fgetc(idx_file) != EOF || ferror(idx_file)) return 3;
    fclose(idx_file);
    if (index->k != 19 || index->w != 19 || index->flag || index->n_alt
            || index->n_seq < 1 || index->n_seq > 1000000) return 2;
    index->index = (int)part;
    mo.mid_occ = (int)mid;
    mm_mapopt_update(&mo,index);
    if (mm_check_opt(&io,&mo)) return 2;
    sequence = (char*)malloc((size_t)length+1);
    if (!sequence) return 3;
    seq_file = fopen(argv[5],"rb");
    if (!seq_file || fseeko(seq_file,(off_t)offset,SEEK_SET)
            || fread(sequence,1,(size_t)length,seq_file) != (size_t)length || ferror(seq_file)) return 3;
    fclose(seq_file);
    sequence[length] = 0;
    for (i = 0; i < length; ++i)
        if (!strchr("ACGTRYSWKMBDHVN",sequence[i]) || !sequence[i]) return 2;
    buffer = mm_tbuf_init();
    if (!buffer) return 3;
    memset(&query,0,sizeof(query));
    query.name = argv[4], query.seq = sequence, query.l_seq = (int)length;
    fprintf(stderr,"QR\t%s\t0\t%d\n",query.name,query.l_seq);
    start = realtime();
    regions = mm_map(index,query.l_seq,sequence,&n_regions,buffer,&mo,query.name);
    fprintf(stderr,"QT\t%s\t0\t%.6f\n",query.name,realtime()-start);
    if (n_regions < 0 || n_regions > 100000 || (n_regions && !regions)) return 3;
    printf("H\tcgat-chain-state\t1\t%s\tasm10\t%d\t%d\t%d\t%d\n",
           MM_VERSION,(int)mid,(int)part,index->k,index->w);
    for (i = 0; i < (int)index->n_seq; ++i) {
        if (!index->seq[i].name || !token(index->seq[i].name)) return 2;
        printf("T\t%d\t%s\t%u\n",i,index->seq[i].name,index->seq[i].len);
    }
    printf("Q\t%s\t%d\t%d\t%d\t%d\n",query.name,query.l_seq,
           buffer->rep_len,buffer->frag_gap,n_regions);
    for (i = 0; i < n_regions; ++i) {
        const mm_reg1_t *r = &regions[i];
        if (r->p) return 2; /* Must NEVER enter base alignment. */
        printf("R\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%u\t%u\t%d\t%d\t%d\t%d\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%u\t%a\n",
               i,r->id,r->parent,r->as,r->cnt,r->score,r->score0,r->qs,r->qe,
               r->rid,r->rs,r->re,(unsigned)r->rev,r->hash,r->subsc,r->n_sub,r->mlen,r->blen,
               (unsigned)r->mapq,(unsigned)r->split,(unsigned)r->inv,(unsigned)r->sam_pri,
               (unsigned)r->seg_split,(unsigned)r->split_inv,(unsigned)r->is_alt,
               (unsigned)r->strand_retained,(unsigned)r->is_spliced,(double)r->div);
        mm_write_paf3(&paf,index,&query,r,buffer->km,mo.flag,buffer->rep_len);
        if (!paf.s || memchr(paf.s,'\n',paf.l) || memchr(paf.s,'\r',paf.l)) return 3;
        printf("P\t%s\n",paf.s);
    }
    printf("END\t%d\n",n_regions);
    if (fflush(stdout) || fflush(stderr)) return 3;
    free(paf.s);
    free(regions);
    free(sequence);
    mm_tbuf_destroy(buffer);
    mm_idx_destroy(index);
    return 0;
}
