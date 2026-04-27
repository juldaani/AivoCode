/** Intentionally broken code for diagnostic tests. */

const x: number = "not a number"; // type-error: string is not number

const y = undefinedName; // name-error: cannot find name

function badFunc(a: number): string {
  return a + 1; // type-error: number is not string
}

function callsWrong(): void {
  badFunc("not a number"); // type-error: string is not number
}
