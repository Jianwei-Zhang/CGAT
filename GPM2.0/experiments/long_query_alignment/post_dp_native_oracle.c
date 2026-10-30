/* Deferred verification harness; no minimap2 source/binary modification.
 * Link against an isolated build of pinned, unmodified upstream v2.31 sources.
 * Calls only the native post-skeleton sort/parent/secondary functions; does NOT
 * exercise alignment or certify that recovered windows provide native state.
 */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include "minimap.h"
#include "mmpriv.h"
/* Include the UNMODIFIED pinned translation unit only in this test harness,
 * making its static mm_update_extra callable. The installed minimap2 is neither
 * rebuilt nor replaced; this file is never part of the Server execution path. */
#include "align.c"

static int read_sequence(uint8_t **out, int length)
{
    static const char alphabet[] = "ACGTN";
    char format[32], *text;
    int i;
    if (length < 1 || length > 1000000) return 2;
    text = (char*)calloc((size_t)length + 1, 1);
    *out = (uint8_t*)calloc((size_t)length, 1);
    if (!text || !*out) return 3;
    snprintf(format, sizeof(format), "%%%ds", length);
    if (scanf(format, text) != 1 || (int)strlen(text) != length) return 2;
    for (i = 0; i < length; ++i) {
        const char *base = strchr(alphabet, text[i]);
        if (!base) return 2;
        (*out)[i] = (uint8_t)(base - alphabet);
    }
    free(text);
    return 0;
}

static int path_score_oracle(void)
{
    int n, qlen, i, j;
    mm_reg1_t *r;
    int8_t mat[25];
    if (scanf("%d %d", &n, &qlen) != 2 || n < 0 || n > 1000 || qlen < 1) return 2;
    r = (mm_reg1_t*)calloc(n? n : 1, sizeof(*r));
    if (!r) return 3;
    ksw_gen_simple_mat(5, mat, 1, 9, 1);
    for (i = 0; i < n; ++i) {
        int nc, rev, status;
        uint8_t *query = 0, *target = 0;
        uint32_t *before;
        mm_reg1_t *x = &r[i];
        if (scanf("%" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNd32 " %d %d",
                  &x->qs, &x->qe, &x->rs, &x->re, &rev, &nc) != 6
                || x->qs < 0 || x->qe > qlen || x->qe <= x->qs
                || x->rs < 0 || x->re <= x->rs || nc < 1 || nc > 10000) return 2;
        x->rev = rev;
        status = read_sequence(&query, x->qe - x->qs);
        if (status) return status;
        status = read_sequence(&target, x->re - x->rs);
        if (status) return status;
        x->p = (mm_extra_t*)calloc(1, sizeof(mm_extra_t)+(size_t)nc*sizeof(uint32_t));
        before = (uint32_t*)calloc((size_t)nc, sizeof(uint32_t));
        if (!x->p || !before) return 3;
        x->p->n_cigar = nc;
        for (j = 0; j < nc; ++j) {
            unsigned length, op;
            if (scanf("%u %u", &length, &op) != 2 || !length || length >= (1U<<28) || op > 2) return 2;
            before[j] = x->p->cigar[j] = length<<4 | op;
        }
        {
            int32_t qs = x->qs, qe = x->qe, rs = x->rs, re = x->re;
            mm_update_extra(x, query, target, mat, 16, 2, 0, 1);
            /* This oracle compares ALREADY normalized paths, not a new path
             * chosen by native left alignment or leading-gap removal. */
            if (x->qs != qs || x->qe != qe || x->rs != rs || x->re != re
                    || x->p->n_cigar != (uint32_t)nc
                    || memcmp(before, x->p->cigar, (size_t)nc*sizeof(uint32_t))) return 4;
        }
        free(before);
        free(query);
        free(target);
    }
    if (qlen >= 500) mm_update_dp_max(qlen, n, r, 0.9f, 1, 9);
    printf("%d\n", n);
    for (i = 0; i < n; ++i) {
        printf("%d %" PRId32 " %" PRId32 " %u %" PRId32 " %" PRId32 " %.17g\n", i,
               r[i].mlen, r[i].blen, (unsigned)r[i].p->n_ambi,
               r[i].p->dp_max0, r[i].p->dp_max, mm_event_identity(&r[i]));
        free(r[i].p);
    }
    free(r);
    return 0;
}

int main(int argc, char **argv)
{
    int n, i, rev;
    mm_reg1_t *r;
    if (argc == 2 && strcmp(argv[1], "--path-rank") == 0) return path_score_oracle();
    if (argc != 1) return 2;
    if (scanf("%d", &n) != 1 || n < 0 || n > 100000) return 2;
    r = (mm_reg1_t*)calloc(n? n : 1, sizeof(*r));
    if (!r) return 3;
    for (i = 0; i < n; ++i) {
        mm_reg1_t *x = &r[i];
        x->p = (mm_extra_t*)calloc(1, sizeof(mm_extra_t));
        if (!x->p) return 3;
        if (scanf("%" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNd32
                  " %d %" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNd32
                  " %" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNd32 " %" SCNu32,
                  &x->qs, &x->qe, &x->rid, &x->rs, &x->re, &rev,
                  &x->score, &x->score0, &x->cnt, &x->mlen, &x->blen,
                  &x->p->dp_max, &x->subsc, &x->n_sub, &x->p->dp_max2, &x->hash) != 16) return 2;
        x->rev = rev;
        x->as = i; /* Stable input identity; these functions never use as. */
    }
    mm_hit_sort(0, &n, r, 0.15f);
    mm_set_parent(0, 0.5f, INT32_MAX, n, r, 11, 0, 0.15f);
    mm_select_sub(0, 0.8f, 38, 50, 0, 8000, &n, r);
    mm_set_sam_pri(n, r);
    printf("%d\n", n);
    for (i = 0; i < n; ++i) {
        printf("%" PRId32 " %" PRId32 " %" PRId32 " %" PRId32 " %" PRId32 " %" PRId32 " %u\n",
               r[i].as, r[i].id, r[i].parent, r[i].subsc, r[i].n_sub,
               r[i].p->dp_max2, (unsigned)r[i].sam_pri);
        free(r[i].p);
    }
    free(r);
    return 0;
}
