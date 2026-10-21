/** Corrective text authored by the client, never an arbitrary service exception. */
export class LocalValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LocalValidationError";
  }
}
