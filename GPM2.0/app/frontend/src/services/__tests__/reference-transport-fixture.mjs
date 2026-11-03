// Test-only producer for synthetic v2 rows. Rust independently verifies the
// shared golden fixture, so this is not the only encoder used for validation.
export function packReferenceWire(v1) {
  return { encoding: "reference-hits-v2", items: v1.items.map(({ hitRows, ...item }) => {
    const previous = item.hitGroups.map(() => Array(8).fill(0n)), bytes = [];
    const unsigned = value => {
      while (value >= 128n) { bytes.push(Number(value & 127n) | 128); value >>= 7n; }
      bytes.push(Number(value));
    };
    for (const [group, ...row] of hitRows) {
      unsigned(BigInt(group));
      row.forEach((value, column) => {
        const current = BigInt(value), delta = current - previous[group][column];
        unsigned(delta < 0n ? -delta * 2n - 1n : delta * 2n);
        previous[group][column] = current;
      });
    }
    return { ...item, hitCount: hitRows.length, hitData: Buffer.from(bytes).toString("base64") };
  }) };
}
