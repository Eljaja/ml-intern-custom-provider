import { Route, Routes } from 'react-router-dom';
import LifecycleLayout from '@/components/Lifecycle/LifecycleLayout';
import TaskDashboard from '@/components/Lifecycle/TaskDashboard';
import TaskKanban from '@/components/Lifecycle/TaskKanban';
import TaskDetail from '@/components/Lifecycle/TaskDetail';

export default function TaskCockpit() {
  return (
    <LifecycleLayout>
      <Routes>
        <Route index element={<TaskDashboard />} />
        <Route path="board" element={<TaskKanban />} />
        <Route path=":taskId" element={<TaskDetail />} />
      </Routes>
    </LifecycleLayout>
  );
}
