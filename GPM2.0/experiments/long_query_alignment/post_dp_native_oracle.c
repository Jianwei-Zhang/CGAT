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

int main(void)
{
    int n, i, rev;
    mm_reg1_t *r;
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
