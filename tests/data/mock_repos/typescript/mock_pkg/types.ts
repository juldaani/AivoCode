/**
 * Shared types for testing definition, type_definition, hover, and call_hierarchy.
 *
 * This module defines classes and functions that are imported by index.ts,
 * enabling cross-file LSP tests (definition jumps, type resolution, references).
 */

/**
 * Base greeter that produces greeting strings.
 */
export class Greeter {
  constructor(private name: string) {}

  /** Return a greeting for this greeter's name. */
  greet(): string {
    return `Hello, ${this.name}!`;
  }
}

/**
 * Factory for creating Greeter instances.
 */
export class GreeterFactory {
  /**
   * Create a Greeter instance.
   *
   * @param name - Name for the greeter.
   * @returns A new Greeter.
   */
  static create(name: string): Greeter {
    return new Greeter(name);
  }
}

/**
 * Create a greeter and return the formatted greeting.
 *
 * Calls GreeterFactory.create and Greeter.greet — useful for
 * testing call_hierarchy across function boundaries.
 */
export function processGreeting(name: string): string {
  const greeter = GreeterFactory.create(name);
  return greeter.greet();
}
