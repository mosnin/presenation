import { cronJobs } from "convex/server";
import { internal } from "./_generated/api";

const crons = cronJobs();

// Fail jobs that never reported back, so nothing sits in `running` forever
// when a Modal callback is lost (see jobs.reapStale).
crons.interval(
  "reap stale jobs",
  { minutes: 10 },
  internal.jobs.reapStale,
  {}
);

export default crons;
