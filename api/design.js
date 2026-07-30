module.exports = async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'OpenRouter API key is missing from environment variables' });
  }

  try {
    const { messages, mode } = req.body;

    // Default system prompt
    let systemPrompt = "You are Design Companion, a premium AI design assistant. Output helpful, concise design advice.";

    // Mode-specific system prompts with strict HTML formatting instructions
    if (mode === 'layout-brainstorm') {
      systemPrompt = `You are a Layout Brainstorming AI for UI/UX design. 
Provide layout suggestions using EXACTLY this HTML structure for each suggestion:
<div class="layout-card">
  <div class="layout-viz z-pattern"> <!-- Change class to bento-grid, command-center, etc as appropriate -->
    <!-- Put placeholder div boxes here to visualize layout -->
    <div class="box"></div> 
  </div>
  <div class="layout-details">
    <h3>Layout Name</h3>
    <p>Description of the layout.</p>
    <div class="pros-cons">
      <span class="pro-icon">✓ Pro point</span>
      <span class="con-icon">✕ Con point</span>
    </div>
    <span class="best-for">Best for: Use case</span>
  </div>
</div>
Use simple HTML. Do not wrap the response in markdown blocks like \`\`\`html.`;
    } else if (mode === 'ui-copy') {
      systemPrompt = `You are a UI Copy Generation AI. Write UI microcopy, error messages, and tooltips.
Provide copy suggestions using EXACTLY this HTML structure for each suggestion:
<div class="copy-card">
  <div class="copy-label">Screen/Context Label</div>
  <div class="copy-content">The actual copy text goes here.</div>
  <button class="btn-copy" onclick="copyToClipboard(this)">Copy Text</button>
</div>
Use simple HTML. Do not wrap the response in markdown blocks like \`\`\`html.`;
    } else if (mode === 'usability-feedback') {
      systemPrompt = `You are a Usability Feedback Analysis AI.
Provide feedback analysis using EXACTLY this HTML structure for each feedback item:
<div class="feedback-item">
  <div class="feedback-header">
    <span class="badge badge-critical">Critical</span> <!-- Or badge-high, badge-medium, badge-low -->
    <strong>Issue Summary</strong>
  </div>
  <ul class="feedback-list">
    <li>Detail 1</li>
    <li>Detail 2</li>
  </ul>
</div>
You can also use metric bars for stats:
<div class="metric-bar-container">
  <div class="metric-label"><span>Label</span><span>%</span></div>
  <div class="metric-bar"><div class="metric-fill bg-red" style="width: 80%;">80%</div></div>
</div>
Use simple HTML. Do not wrap the response in markdown blocks like \`\`\`html.`;
    }

    const openRouterMessages = [
      { role: 'system', content: systemPrompt },
      ...messages.map(m => ({
        role: m.sender === 'user' ? 'user' : 'assistant',
        content: m.text
      }))
    ];

    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + apiKey,
        'HTTP-Referer': 'https://careem-design-companion.vercel.app/', // Update to actual domain later
        'X-Title': 'Design Companion Prototype',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'google/gemma-2-9b-it', // Official Gemma 2 9B Instruct model on OpenRouter
        messages: openRouterMessages,
      })
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('OpenRouter API Error:', errorText);
      try {
        const errJson = JSON.parse(errorText);
        return res.status(response.status).json({ error: errJson.error?.message || 'OpenRouter API Error' });
      } catch (e) {
        return res.status(response.status).json({ error: errorText || 'Failed to fetch from OpenRouter API' });
      }
    }

    const data = await response.json();
    let replyText = data.choices[0].message.content;
    
    // Strip markdown formatting if the model still outputs it despite the prompt
    replyText = replyText.replace(/\`\`\`html\\n?/g, '').replace(/\`\`\`/g, '');

    return res.status(200).json({ text: replyText });

  } catch (error) {
    console.error('Error in chat handler:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}
