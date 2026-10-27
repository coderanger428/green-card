import toast from 'react-hot-toast';

export const copyText = async (value) => {
  await navigator.clipboard.writeText(String(value || ''));
  toast.success('Copied.');
};
