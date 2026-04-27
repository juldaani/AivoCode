export const MAX_ITEMS = 10;

export interface Greeter {
  greet(name: string): string;
}

export class FriendlyGreeter implements Greeter {
  greet(name: string): string {
    return `Hello, ${name}!`;
  }
}

export class FormalGreeter implements Greeter {
  greet(name: string): string {
    return `Good day, ${name}.`;
  }
}

export function createGreeter(style: "friendly" | "formal"): Greeter {
  if (style === "friendly") {
    return new FriendlyGreeter();
  }
  return new FormalGreeter();
}

export function formatMessage(message: string, prefix = "INFO"): string {
  return `[${prefix}] ${message}`;
}
