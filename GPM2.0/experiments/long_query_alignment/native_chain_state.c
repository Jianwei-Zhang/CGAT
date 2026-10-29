/* Read pre-DP state through the UNMODIFIED minimap2 v2.31 library API.
 * No CIGAR/DP mapping, no binary interposition, no patch to minimap2 sources.
 * Build only with the pinned clean source via build_native_chain_state.py.
 * Upstream license: MINIMAP2_LICENSE.txt. This companion is NOT minimap2.
 */
#define _FILE_OFFSET_BITS 64
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <locale.h>
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
