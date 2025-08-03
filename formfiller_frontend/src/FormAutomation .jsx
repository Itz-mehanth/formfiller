import React, { useState, useEffect, useCallback } from 'react';

// A simple utility to format question types for display
const formatQuestionType = (type) => {
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase());
};

const FormAutomation = () => {
  // --- STATE MANAGEMENT ---
  const [formUrl, setFormUrl] = useState('');
  const [questions, setQuestions] = useState([]);
  const [automationSettings, setAutomationSettings] = useState({
    totalSubmissions: 50,
    threads: 2,
    delay: 5,
  });
  const [automationStatus, setAutomationStatus] = useState({
    status: 'idle',
    message: 'Ready to start',
  });
  const [isLoading, setIsLoading] = useState(false);

  // --- API HANDLERS ---

  const handleAnalyzeForm = async () => {
    if (!formUrl) {
      alert('Please enter a valid Google Forms URL.');
      return;
    }
    setIsLoading(true);
    setQuestions([]);
    try {
      const response = await fetch('https://formfiller-mykv.onrender.com/analyze-form', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ form_url: formUrl }),
      });
      const data = await response.json();
      if (data.success) {
        setQuestions(data.questions);
      } else {
        alert('Error: ' + data.error);
      }
    } catch (error) {
      alert('An error occurred: ' + error.message);
    }
    setIsLoading(false);
  };

  const pollAutomationStatus = useCallback(() => {
    const intervalId = setInterval(async () => {
      try {
        const response = await fetch('https://formfiller-mykv.onrender.com/automation-status');
        const data = await response.json();
        setAutomationStatus(data);
        if (['completed', 'stopped', 'error'].includes(data.status)) {
          clearInterval(intervalId);
          setIsLoading(false);
        }
      } catch (error) {
        console.error('Polling error:', error);
        clearInterval(intervalId);
        setIsLoading(false);
      }
    }, 2000);
    return () => clearInterval(intervalId);
  }, []);

  const handleStartAutomation = async () => {
    if (questions.length === 0) {
      alert('Please analyze a form first.');
      return;
    }
    for (const q of questions) {
      if ((q.type === 'multiple_choice_radio' || q.type === 'linear_scale') && Math.abs(q.options.reduce((s, o) => s + parseInt(o.percentage, 10), 0) - 100) > 1) {
        alert(`Error: Percentages for "${q.title}" must sum to 100%.`);
        return;
      }
      if ((q.type === 'short_answer' || q.type === 'paragraph') && (!q.answer_pool || q.answer_pool.join('').trim() === '')) {
        alert(`Error: Please provide answers in the answer pool for "${q.title}".`);
        return;
      }
    }
    setIsLoading(true);
    setAutomationStatus({ status: 'running', message: 'Initializing automation...' });
    try {
      const response = await fetch('https://formfiller-mykv.onrender.com/start-automation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ form_url: formUrl, questions, settings: automationSettings }),
      });
      const data = await response.json();
      if (data.success) {
        pollAutomationStatus();
      } else {
        setAutomationStatus({ status: 'error', message: data.error });
        setIsLoading(false);
      }
    } catch (error) {
      setAutomationStatus({ status: 'error', message: error.message });
      setIsLoading(false);
    }
  };

  const handleStopAutomation = async () => {
    setAutomationStatus(prev => ({ ...prev, message: 'Sending stop signal...' }));
    try {
      await fetch('https://formfiller-mykv.onrender.com/stop-automation', { method: 'POST' });
    } catch (error) {
      setAutomationStatus({ status: 'error', message: 'Error sending stop signal: ' + error.message });
    }
  };

  // --- UI STATE HANDLERS ---
  const handleSettingsChange = (e) => {
    const { name, value, min, max } = e.target;
    let intValue = parseInt(value, 10) || 0;

    // Enforce min/max constraints
    if (min && intValue < parseInt(min, 10)) {
        intValue = parseInt(min, 10);
    }
    if (max && intValue > parseInt(max, 10)) {
        intValue = parseInt(max, 10);
    }

    setAutomationSettings(prev => ({ ...prev, [name]: intValue }));
  };

  const handlePercentageChange = (qIndex, oIndex, value) => {
    const updatedQuestions = [...questions];
    updatedQuestions[qIndex].options[oIndex].percentage = parseInt(value, 10) || 0;
    setQuestions(updatedQuestions);
  };

  const handleAnswerPoolChange = (qIndex, value) => {
    const updatedQuestions = [...questions];
    updatedQuestions[qIndex].answer_pool = value.split(',').map(item => item.trim());
    setQuestions(updatedQuestions);
  };
  
  const getTotalPercentage = (question) => {
    if (!question.options) return 0;
    return question.options.reduce((sum, opt) => sum + (opt.percentage || 0), 0);
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-3xl">
        <div className="bg-white/80 backdrop-blur-md rounded-2xl shadow-xl p-8 border border-white/30">
          <h1 className="text-3xl font-bold text-center text-gray-800 mb-6">Google Forms Automation</h1>

          {/* URL Input */}
          <div className="flex gap-2 mb-4">
            <input
              type="text" value={formUrl} onChange={(e) => setFormUrl(e.target.value)}
              placeholder="Enter Google Form URL"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={isLoading}
            />
            <button onClick={handleAnalyzeForm} disabled={isLoading}
              className="px-6 py-2 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 disabled:bg-gray-400">
              {isLoading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>

          {/* --- SETTINGS INPUTS WITH VALIDATION --- */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700">Total Submissions</label>
              <input
                type="number" name="totalSubmissions" value={automationSettings.totalSubmissions}
                onChange={handleSettingsChange} disabled={isLoading}
                min="1" // Cannot be less than 1
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Threads</label>
              <input
                type="number" name="threads" value={automationSettings.threads}
                onChange={handleSettingsChange} disabled={isLoading}
                min="1" // Cannot be less than 1
                max="10" // A sensible upper limit to prevent crashes
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Delay (seconds)</label>
              <input
                type="number" name="delay" value={automationSettings.delay}
                onChange={handleSettingsChange} disabled={isLoading}
                min="0" // Cannot be negative
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>

          {/* Automation Controls & Status */}
          <div className="bg-gray-50 rounded-lg p-4 mb-6 border">
             <div className="flex justify-between items-center">
                 <div className="flex gap-4">
                     <button onClick={handleStartAutomation} disabled={isLoading || questions.length === 0}
                        className="px-6 py-2 bg-green-600 text-white font-semibold rounded-lg shadow-md hover:bg-green-700 disabled:bg-gray-400">
                        Start Automation
                      </button>
                      {automationStatus.status === 'running' && (
                        <button onClick={handleStopAutomation}
                          className="px-6 py-2 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700">
                          Stop
                        </button>
                      )}
                 </div>
                 <div className="text-right">
                     <p className={`font-semibold ${automationStatus.status === 'error' ? 'text-red-500' : 'text-gray-700'}`}>
                       Status: {automationStatus.status}
                     </p>
                     <p className="text-sm text-gray-500">{automationStatus.message}</p>
                 </div>
             </div>
          </div>
          
          {/* Questions Configuration */}
          {questions.length > 0 && (
            <div className="bg-white/70 backdrop-blur-sm rounded-2xl p-6 shadow-lg border border-white/20">
              <h2 className="text-xl font-semibold text-gray-800 mb-4">Response Distribution</h2>
              <div className="space-y-6 max-h-[40vh] overflow-y-auto pr-2">
                {questions.map((question, qIndex) => (
                  <div key={qIndex} className="border border-gray-200 rounded-lg p-4 bg-white/50">
                    <h3 className="font-medium text-gray-800 mb-3">
                      Q{qIndex + 1}: {question.title}
                      <span className="ml-2 text-xs font-normal bg-blue-100 text-blue-800 px-2 py-1 rounded-full">{formatQuestionType(question.type)}</span>
                    </h3>
                    {question.options && (
                      <>
                        <div className="grid gap-3">
                          {question.options.map((option, oIndex) => (
                            <div key={oIndex} className="flex items-center gap-3">
                              <span className="flex-1 text-sm text-gray-700">{option.text}</span>
                              <div className="flex items-center gap-2">
                                <input type="number" value={option.percentage} onChange={(e) => handlePercentageChange(qIndex, oIndex, e.target.value)}
                                  className="w-16 px-2 py-1 text-center border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500" />
                                <span className="text-sm text-gray-500">%</span>
                              </div>
                            </div>
                          ))}
                        </div>
                        {question.type !== 'multiple_choice_checkbox' && (
                          <div className={`mt-2 text-right text-sm ${getTotalPercentage(question) === 100 ? 'text-green-600' : 'text-red-600'}`}>
                            Total: {getTotalPercentage(question)}%
                          </div>
                        )}
                      </>
                    )}
                    {question.answer_pool && (
                      <div className="mt-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Answer Pool (comma-separated)</label>
                        <textarea value={question.answer_pool.join(', ')} onChange={(e) => handleAnswerPoolChange(qIndex, e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm" rows="2" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default FormAutomation;