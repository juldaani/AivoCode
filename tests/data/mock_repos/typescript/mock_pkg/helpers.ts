import { Greeter, createGreeter, formatMessage } from "./index";

export function welcomeUser(name: string): string {
  const greeter = createGreeter("friendly");
  const greeting = greeter.greet(name);
  return formatMessage(greeting, "WELCOME");
}

export class UserService {
  private users: string[] = [];

  addUser(name: string): void {
    this.users.push(name);
  }

  getUsers(): string[] {
    return [...this.users];
  }
}
