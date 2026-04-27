/**
 * Shared types for testing definition, type_definition, hover, and call_hierarchy.
 *
 * This module defines classes and functions that are imported by index.ts,
 * enabling cross-file LSP tests (definition jumps, type resolution, references).
 * Names use the "Type" prefix to avoid collisions with index.ts's local
 * Greeter/GreeterFactory symbols.
 */

/**
 * Base greeter that produces greeting strings.
 */
export class TypeGreeter {  // MARK:class_def
  constructor(private name: string) {}

  /** Return a greeting for this greeter's name. */
  greet(): string {  // MARK:greet_def
    return `Hello, ${this.name}!`;
  }
}

/**
 * Factory for creating TypeGreeter instances.
 */
export class TypeGreeterFactory {
  /**
   * Create a TypeGreeter instance.
   *
   * @param name - Name for the greeter.
   * @returns A new TypeGreeter.
   */
  static create(name: string): TypeGreeter {
    return new TypeGreeter(name);
  }
}

/**
 * Create a greeter and return the formatted greeting.
 *
 * Calls TypeGreeterFactory.create and TypeGreeter.greet — useful for
 * testing call_hierarchy across function boundaries.
 */
export function processGreeting(name: string): string {
  const greeter = TypeGreeterFactory.create(name);
  return greeter.greet();
}
