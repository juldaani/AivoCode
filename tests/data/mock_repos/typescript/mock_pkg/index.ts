/**
 * Main module exports for multi-language LSP testing.
 */

export const MAX_ITEMS = 10;

/**
 * Interface for greeting implementations.
 */
export interface Greeter {
  /** Return a greeting for the given name. */
  greet(name: string): string;
}

/**
 * Friendly greeting style — uses casual language.
 */
export class FriendlyGreeter implements Greeter {
  /** Return a friendly greeting. */
  greet(name: string): string {
    return `Hello, ${name}!`;
  }
}

/**
 * Formal greeting style — uses polite language.
 */
export class FormalGreeter implements Greeter {
  /** Return a formal greeting. */
  greet(name: string): string {
    return `Good day, ${name}.`;
  }
}

/**
 * Create a greeter for the given style.
 *
 * @param style - "friendly" or "formal"
 * @returns A Greeter instance.
 */
export function createGreeter(style: "friendly" | "formal"): Greeter {
  if (style === "friendly") {
    return new FriendlyGreeter();
  }
  return new FormalGreeter();
}

/**
 * Format a message with a prefix tag.
 */
export function formatMessage(message: string, prefix = "INFO"): string {
  return `[${prefix}] ${message}`;
}

// --- Cross-file calls (imported from types.ts) ---

import { TypeGreeter, TypeGreeterFactory, processGreeting } from "./types";  // MARK:import

/**
 * Cross-file call chain: create a TypeGreeter via factory, then greet.
 *
 * Calls TypeGreeterFactory.create and TypeGreeter.greet from types.ts —
 * useful for testing definition jumps and call_hierarchy across files.
 */
export function createAndGreet(name: string): string {  // MARK:create_def
  // MARK:greeter_var
  const greeter = TypeGreeterFactory.create(name);
  // MARK:greet_call
  return greeter.greet();
}

/**
 * Top of call hierarchy: calls createAndGreet and processGreeting.
 *
 * 4-level call chain:
 * fullGreeting → createAndGreet → TypeGreeterFactory.create → TypeGreeter.greet
 * fullGreeting → processGreeting (cross-file to types.ts)
 */
export function fullGreeting(name: string): string {  // MARK:full_def
  const g1 = createAndGreet(name);
  const g2 = processGreeting(name);
  return `${g1} | ${g2}`;
}
