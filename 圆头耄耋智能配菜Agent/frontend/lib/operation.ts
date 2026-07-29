export type OperationHandle = {
  epoch: number;
  signal: AbortSignal;
};

export class OperationEpoch {
  private epoch = 0;
  private controller: AbortController | null = null;

  begin(): OperationHandle {
    this.controller?.abort();
    this.epoch += 1;
    this.controller = new AbortController();
    return {
      epoch: this.epoch,
      signal: this.controller.signal,
    };
  }

  cancel(): void {
    this.controller?.abort();
    this.controller = null;
    this.epoch += 1;
  }

  canCommit(handle: OperationHandle): boolean {
    return (
      !handle.signal.aborted &&
      this.controller?.signal === handle.signal &&
      handle.epoch === this.epoch
    );
  }
}
