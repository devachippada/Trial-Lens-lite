/** Pure client-side validation for the trial comparison form. */

const NCT_PATTERN = /^NCT\d{8}$/i;

export function validateComparisonInput(nctIdA: string, nctIdB: string): string | null {
  const a = nctIdA.trim();
  const b = nctIdB.trim();

  if (!a || !b) return "Enter both trial NCT numbers to compare.";

  if (!NCT_PATTERN.test(a) || !NCT_PATTERN.test(b)) {
    return 'NCT numbers look like "NCT" followed by 8 digits, e.g. NCT01234567.';
  }

  if (a.toUpperCase() === b.toUpperCase()) {
    return "Choose two different trials to compare.";
  }

  return null;
}
