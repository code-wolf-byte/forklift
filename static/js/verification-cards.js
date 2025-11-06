/* Runtime injection for verification step cards to mimic Webspark card-arrangement behaviour. */
(function () {
  const CARD_BASE_CLASSES = ['sc-fqkvVR', 'glpyHd', 'card', 'cards-components'];

  const createElement = (tag, className, attrs) => {
    const el = document.createElement(tag);
    if (className) {
      className.split(/\s+/).filter(Boolean).forEach(cls => el.classList.add(cls));
    }
    if (attrs) {
      Object.entries(attrs).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          el.setAttribute(key, value);
        }
      });
    }
    return el;
  };

  const renderAction = (action) => {
    const wrapper = createElement('div', 'card-button', { 'data-testid': 'card-button' });
    if (!action || !action.type) {
      return wrapper;
    }

    const className = action.class_name || 'btn btn-maroon';
    const isDisabled = Boolean(action.disabled);
    const ariaDisabled = isDisabled ? 'true' : null;

    if (action.type === 'form') {
      const form = document.createElement('form');
      form.method = action.method || 'get';
      if (action.url) {
        form.action = action.url;
      }
      const button = createElement('button', className, { type: 'submit' });
      button.textContent = action.label || '';
      if (isDisabled) {
        button.disabled = true;
        if (ariaDisabled) {
          button.setAttribute('aria-disabled', ariaDisabled);
        }
      }
      form.appendChild(button);
      wrapper.appendChild(form);
      return wrapper;
    }

    if (action.type === 'link') {
      const anchor = createElement('a', className);
      anchor.textContent = action.label || '';
      if (isDisabled) {
        anchor.classList.add('disabled');
        anchor.setAttribute('aria-disabled', 'true');
        anchor.href = '#';
      } else if (action.url) {
        anchor.href = action.url;
      }
      if (action.target && !isDisabled) {
        anchor.target = action.target;
      }
      if (action.rel && !isDisabled) {
        anchor.rel = action.rel;
      }
      wrapper.appendChild(anchor);
      return wrapper;
    }

    if (action.type === 'button') {
      const button = createElement('button', className, { type: 'button' });
      button.textContent = action.label || '';
      if (isDisabled) {
        button.disabled = true;
        if (ariaDisabled) {
          button.setAttribute('aria-disabled', ariaDisabled);
        }
      }
      wrapper.appendChild(button);
      return wrapper;
    }

    if (action.type === 'html') {
      wrapper.innerHTML = action.html || '';
    }

    return wrapper;
  };

  const buildCard = (config) => {
    const wrapper = document.getElementById(config.id);
    if (!wrapper) {
      return;
    }

    wrapper.innerHTML = '';
    const cardClasses = CARD_BASE_CLASSES.slice();
    if (config.class_name) {
      cardClasses.push(...config.class_name.split(/\s+/).filter(Boolean));
    }

    const card = createElement('div', cardClasses.join(' '), { 'data-testid': 'card-container' });

    const header = createElement('div', 'card-header', { 'data-testid': 'card-title' });
    const title = createElement('h3', 'card-title');
    title.textContent = config.title || '';
    header.appendChild(title);
    card.appendChild(header);

    const body = createElement('div', 'card-body', { 'data-testid': 'card-body' });
    const bodyContent = document.createElement('div');
    if (config.body_html) {
      bodyContent.innerHTML = config.body_html;
    }
    if (config.status_html) {
      const statusContainer = document.createElement('div');
      statusContainer.innerHTML = config.status_html;
      bodyContent.appendChild(statusContainer);
    }
    body.appendChild(bodyContent);
    card.appendChild(body);

    if (Array.isArray(config.actions) && config.actions.length) {
      const actionsContainer = createElement('div', 'card-buttons');
      config.actions.forEach(action => {
        actionsContainer.appendChild(renderAction(action));
      });
      card.appendChild(actionsContainer);
    }

    wrapper.appendChild(card);
  };

  const init = () => {
    const dataEl = document.getElementById('verification-cards-data');
    if (!dataEl) {
      return;
    }

    let cards;
    try {
      cards = JSON.parse(dataEl.textContent || '[]');
    } catch (err) {
      console.error('Failed to parse verification cards data.', err);
      return;
    }

    if (!Array.isArray(cards)) {
      return;
    }

    cards.forEach(buildCard);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
