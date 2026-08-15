"""Generate Java source files for the Flink LongestSessionPerJob job.

This module provides functions to generate:
- TaskEvent.java: POJO for task events from Google cluster trace
- JobEvent.java: POJO for job events from Google cluster trace  
- LongestSessionPerJob.java: Main Flink job implementation

The job identifies stages of task SUBMIT events using session windows,
finds the stage with the most tasks per finished job, and outputs results.
"""
import os


def generate_task_event_java():
    """Return the TaskEvent.java source code string.
    
    TaskEvent represents a task event from the Google cluster trace.
    CSV columns: timestamp, missingInfo, jobId, taskIndex, machineId,
    eventType, user, schedulingClass, priority, cpuRequest, memoryRequest,
    diskSpaceRequest, differentMachinesRestriction
    """
    return '''package clusterdata.datatypes;

import java.io.Serializable;

public class TaskEvent implements Serializable {
    public long timestamp;
    public String missingInfo;
    public long jobId;
    public int taskIndex;
    public String machineId;
    public int eventType;
    public String user;
    public int schedulingClass;
    public int priority;
    public double cpuRequest;
    public double memoryRequest;
    public double diskSpaceRequest;
    public int differentMachinesRestriction;

    public TaskEvent() {}

    public static TaskEvent fromString(String line) {
        String[] parts = line.split(",", -1);
        if (parts.length < 6) return null;
        try {
            TaskEvent e = new TaskEvent();
            e.timestamp = parts[0].isEmpty() ? 0 : Long.parseLong(parts[0]);
            e.missingInfo = parts[1];
            e.jobId = parts[2].isEmpty() ? -1 : Long.parseLong(parts[2]);
            e.taskIndex = parts[3].isEmpty() ? -1 : Integer.parseInt(parts[3]);
            e.machineId = parts[4];
            e.eventType = parts[5].isEmpty() ? -1 : Integer.parseInt(parts[5]);
            if (parts.length > 6) e.user = parts[6];
            if (parts.length > 7) e.schedulingClass = parts[7].isEmpty() ? 0 : Integer.parseInt(parts[7]);
            if (parts.length > 8) e.priority = parts[8].isEmpty() ? 0 : Integer.parseInt(parts[8]);
            if (parts.length > 9) e.cpuRequest = parts[9].isEmpty() ? 0 : Double.parseDouble(parts[9]);
            if (parts.length > 10) e.memoryRequest = parts[10].isEmpty() ? 0 : Double.parseDouble(parts[10]);
            if (parts.length > 11) e.diskSpaceRequest = parts[11].isEmpty() ? 0 : Double.parseDouble(parts[11]);
            if (parts.length > 12) e.differentMachinesRestriction = parts[12].isEmpty() ? 0 : Integer.parseInt(parts[12]);
            return e;
        } catch (Exception ex) {
            return null;
        }
    }

    public long getTimestamp() { return timestamp; }
    public long getJobId() { return jobId; }
    public int getEventType() { return eventType; }
    public int getTaskIndex() { return taskIndex; }

    @Override
    public String toString() {
        return "TaskEvent{" + "timestamp=" + timestamp + ", jobId=" + jobId + ", taskIndex=" + taskIndex + ", eventType=" + eventType + "}";
    }
}
'''


def generate_job_event_java():
    """Return the JobEvent.java source code string.
    
    JobEvent represents a job event from the Google cluster trace.
    CSV columns: timestamp, missingInfo, jobId, eventType, user,
    schedulingClass, jobName, logicalJobName
    """
    return '''package clusterdata.datatypes;

import java.io.Serializable;

public class JobEvent implements Serializable {
    public long timestamp;
    public String missingInfo;
    public long jobId;
    public int eventType;
    public String user;
    public int schedulingClass;
    public String jobName;
    public String logicalJobName;

    public JobEvent() {}

    public static JobEvent fromString(String line) {
        String[] parts = line.split(",", -1);
        if (parts.length < 4) return null;
        try {
            JobEvent e = new JobEvent();
            e.timestamp = parts[0].isEmpty() ? 0 : Long.parseLong(parts[0]);
            e.missingInfo = parts[1];
            e.jobId = parts[2].isEmpty() ? -1 : Long.parseLong(parts[2]);
            e.eventType = parts[3].isEmpty() ? -1 : Integer.parseInt(parts[3]);
            if (parts.length > 4) e.user = parts[4];
            if (parts.length > 5) e.schedulingClass = parts[5].isEmpty() ? 0 : Integer.parseInt(parts[5]);
            if (parts.length > 6) e.jobName = parts[6];
            if (parts.length > 7) e.logicalJobName = parts[7];
            return e;
        } catch (Exception ex) {
            return null;
        }
    }

    public long getTimestamp() { return timestamp; }
    public long getJobId() { return jobId; }
    public int getEventType() { return eventType; }

    @Override
    public String toString() {
        return "JobEvent{" + "timestamp=" + timestamp + ", jobId=" + jobId + ", eventType=" + eventType + "}";
    }
}
'''


def generate_longest_session_java(session_gap_seconds=600):
    """Return the LongestSessionPerJob.java source code string.
    
    The job:
    1. Reads task events, filters for SUBMIT (eventType=0)
    2. Applies session windows with configurable gap (default 10 min)
    3. Counts tasks per session per job
    4. Reads job events, filters for FINISH (eventType=4)
    5. Joins session counts with finished jobs using KeyedCoProcessFunction
    6. Emits (jobId, maxSessionCount) for each finished job
    
    Uses event-time timer at Long.MAX_VALUE-1 to emit final results
    after all bounded data is processed.
    """
    return '''package clusterdata.query;

import clusterdata.datatypes.JobEvent;
import clusterdata.datatypes.TaskEvent;
import clusterdata.utils.AppBase;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.functions.FlatMapFunction;
import org.apache.flink.api.common.functions.MapFunction;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.api.java.tuple.Tuple2;
import org.apache.flink.api.java.utils.ParameterTool;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.co.KeyedCoProcessFunction;
import org.apache.flink.streaming.api.functions.windowing.WindowFunction;
import org.apache.flink.streaming.api.windowing.assigners.EventTimeSessionWindows;
import org.apache.flink.streaming.api.windowing.time.Time;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

import java.time.Duration;

public class LongestSessionPerJob extends AppBase {

    public static void main(String[] args) throws Exception {

        ParameterTool params = ParameterTool.fromArgs(args);
        String taskInput = params.get("task_input", null);
        String jobInput = params.get("job_input", null);
        String outputPath = params.get("output", null);
        System.out.println("task_input  " + taskInput);
        System.out.println("job_input  " + jobInput);
        final int sesssize = params.getInt("sesssize", ''' + str(session_gap_seconds) + ''');

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(1);

        // Read task events
        DataStream<TaskEvent> taskEventsStream = env
                .readTextFile(taskInput)
                .flatMap(new FlatMapFunction<String, TaskEvent>() {
                    @Override
                    public void flatMap(String line, Collector<TaskEvent> out) {
                        TaskEvent e = TaskEvent.fromString(line);
                        if (e != null) out.collect(e);
                    }
                }).returns(TaskEvent.class);

        // Read job events
        DataStream<JobEvent> jobEventsStream = env
                .readTextFile(jobInput)
                .flatMap(new FlatMapFunction<String, JobEvent>() {
                    @Override
                    public void flatMap(String line, Collector<JobEvent> out) {
                        JobEvent e = JobEvent.fromString(line);
                        if (e != null) out.collect(e);
                    }
                }).returns(JobEvent.class);

        // Filter SUBMIT task events and assign watermarks
        DataStream<TaskEvent> submitEvents = taskEventsStream
                .filter(e -> e.eventType == 0)
                .assignTimestampsAndWatermarks(
                        WatermarkStrategy.<TaskEvent>forBoundedOutOfOrderness(Duration.ofSeconds(0))
                                .withTimestampAssigner((event, ts) -> event.timestamp / 1000)
                );

        // Session window: count SUBMIT events per session per job
        DataStream<Tuple2<Long, Integer>> sessionCounts = submitEvents
                .keyBy(e -> e.jobId)
                .window(EventTimeSessionWindows.withGap(Time.seconds(sesssize)))
                .apply(new WindowFunction<TaskEvent, Tuple2<Long, Integer>, Long, TimeWindow>() {
                    @Override
                    public void apply(Long jobId, TimeWindow window, Iterable<TaskEvent> input, Collector<Tuple2<Long, Integer>> out) {
                        int count = 0;
                        for (TaskEvent e : input) {
                            count++;
                        }
                        out.collect(new Tuple2<>(jobId, count));
                    }
                });

        // Finished jobs
        DataStream<Tuple2<Long, Boolean>> finishedJobs = jobEventsStream
                .filter(e -> e.eventType == 4)
                .map(new MapFunction<JobEvent, Tuple2<Long, Boolean>>() {
                    @Override
                    public Tuple2<Long, Boolean> map(JobEvent e) {
                        return new Tuple2<>(e.jobId, true);
                    }
                }).returns(Types.TUPLE(Types.LONG, Types.BOOLEAN));

        // Connect and output using timer-based approach
        DataStream<String> result = sessionCounts
                .connect(finishedJobs)
                .keyBy(t -> t.f0, t -> t.f0)
                .process(new KeyedCoProcessFunction<Long, Tuple2<Long, Integer>, Tuple2<Long, Boolean>, String>() {
                    private transient ValueState<Integer> maxCount;
                    private transient ValueState<Boolean> isFinished;

                    @Override
                    public void open(Configuration parameters) {
                        maxCount = getRuntimeContext().getState(
                                new ValueStateDescriptor<>("maxCount", Integer.class));
                        isFinished = getRuntimeContext().getState(
                                new ValueStateDescriptor<>("isFinished", Boolean.class));
                    }

                    @Override
                    public void processElement1(Tuple2<Long, Integer> value, Context ctx, Collector<String> out) throws Exception {
                        Integer current = maxCount.value();
                        if (current == null || value.f1 > current) {
                            maxCount.update(value.f1);
                        }
                        ctx.timerService().registerEventTimeTimer(Long.MAX_VALUE - 1);
                    }

                    @Override
                    public void processElement2(Tuple2<Long, Boolean> value, Context ctx, Collector<String> out) throws Exception {
                        isFinished.update(true);
                        ctx.timerService().registerEventTimeTimer(Long.MAX_VALUE - 1);
                    }

                    @Override
                    public void onTimer(long timestamp, OnTimerContext ctx, Collector<String> out) throws Exception {
                        Boolean finished = isFinished.value();
                        Integer mc = maxCount.value();
                        if (finished != null && finished && mc != null) {
                            out.collect("(" + ctx.getCurrentKey() + "," + mc + ")");
                        }
                    }
                });

        // Write output
        if (outputPath != null) {
            result.writeAsText(outputPath, org.apache.flink.core.fs.FileSystem.WriteMode.OVERWRITE)
                    .setParallelism(1);
        } else {
            result.print();
        }

        env.execute("LongestSessionPerJob");
    }
}
'''


def write_java_sources(workspace_dir):
    """Write all Java source files to the workspace directory.
    
    Args:
        workspace_dir: Path to the workspace root (e.g., /app/workspace)
    """
    src_base = os.path.join(workspace_dir, 'src', 'main', 'java', 'clusterdata')
    
    # Create directories
    datatypes_dir = os.path.join(src_base, 'datatypes')
    query_dir = os.path.join(src_base, 'query')
    os.makedirs(datatypes_dir, exist_ok=True)
    os.makedirs(query_dir, exist_ok=True)
    
    # Write TaskEvent.java
    with open(os.path.join(datatypes_dir, 'TaskEvent.java'), 'w') as f:
        f.write(generate_task_event_java())
    
    # Write JobEvent.java
    with open(os.path.join(datatypes_dir, 'JobEvent.java'), 'w') as f:
        f.write(generate_job_event_java())
    
    # Write LongestSessionPerJob.java
    with open(os.path.join(query_dir, 'LongestSessionPerJob.java'), 'w') as f:
        f.write(generate_longest_session_java())
    
    print(f"Java sources written to {src_base}")

