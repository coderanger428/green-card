import ReactPaginate from 'react-paginate';
import ui from '../styles/ui.module.css';

export const UsersPagination = ({ page, pageCount, onPageChange }) => {
  if (pageCount <= 1) {
    return null;
  }
  return (
    <ReactPaginate
      breakLabel="…"
      nextLabel="Next"
      previousLabel="Previous"
      onPageChange={(event) => onPageChange(event.selected + 1)}
      forcePage={Math.max(0, page - 1)}
      pageRangeDisplayed={3}
      marginPagesDisplayed={1}
      pageCount={pageCount}
      renderOnZeroPageCount={null}
      containerClassName={ui['pagination']}
      pageClassName={ui['pagination-item']}
      pageLinkClassName={ui['pagination-link']}
      previousClassName={ui['pagination-item']}
      previousLinkClassName={ui['pagination-link']}
      nextClassName={ui['pagination-item']}
      nextLinkClassName={ui['pagination-link']}
      breakClassName={ui['pagination-item']}
      breakLinkClassName={ui['pagination-link']}
      activeClassName={ui['active']}
      disabledClassName={ui['disabled']}
    />
  );
};
